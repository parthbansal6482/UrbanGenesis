"""
etl/stac_streamer.py

Streams Sentinel-2 L2A tiles directly from Microsoft Planetary Computer STAC API.
NO full scene downloads. Each 512x512 tile is fetched on demand, used, and discarded.

Why Planetary Computer:
- Free, no credentials required for anonymous access (token auto-refreshed)
- Global Sentinel-2 L2A collection, updated every 5 days
- Supports COG (Cloud Optimized GeoTIFF) — enables windowed reads over HTTP
  so only the bytes for your specific tile window are transferred
- Typical data transferred per tile: ~2MB instead of ~1.5GB for a full scene

Storage guarantee: This module NEVER writes a full scene to disk.
Only 512x512 tile GeoTIFFs (one per tile, ~1–3MB each) are written.
All tiles must be cleared after inference via the cleanup_tiles() function.
"""

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

PLANETARY_COMPUTER_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
SENTINEL2_COLLECTION = "sentinel-2-l2a"

# Bands needed: Red (B04), Green (B03), Blue (B02), NIR (B08)
REQUIRED_BANDS = ["B04", "B03", "B02", "B08"]


def _try_import_stac():
    """Lazy imports — only needed at stream time, not at import time."""
    try:
        import pystac_client
        import planetary_computer
        return pystac_client, planetary_computer
    except ImportError as e:
        raise ImportError(
            f"STAC streaming requires pystac-client and planetary-computer. "
            f"Install with: pip install pystac-client planetary-computer\n"
            f"Original error: {e}"
        )


class STACStreamer:
    def __init__(self, config: dict):
        self.config = config
        self.tile_size = config["tiling"]["tile_size"]
        self.overlap = config["tiling"]["overlap"]
        self.cloud_max = config["sentinel"]["cloud_cover_max"]
        self._client = None  # lazy-initialised

    @property
    def client(self):
        if self._client is None:
            pystac_client, planetary_computer = _try_import_stac()
            self._client = pystac_client.Client.open(
                PLANETARY_COMPUTER_URL,
                modifier=planetary_computer.sign_inplace,
            )
        return self._client

    def search_scenes(self, bbox: List[float], year: int) -> list:
        """
        Search for available Sentinel-2 scenes for a bbox and year.
        Returns list of STAC items sorted by cloud cover (least cloudy first).
        bbox: [min_lon, min_lat, max_lon, max_lat]
        """
        _, _ = _try_import_stac()  # fail fast if not installed
        date_range = f"{year}-01-01/{year}-12-31"
        search = self.client.search(
            collections=[SENTINEL2_COLLECTION],
            bbox=bbox,
            datetime=date_range,
            query={"eo:cloud_cover": {"lt": self.cloud_max}},
            sortby=[{"field": "eo:cloud_cover", "direction": "asc"}],
            max_items=3,
        )
        items = list(search.items())
        if not items:
            logger.warning(
                f"No scenes found for bbox={bbox}, year={year}, "
                f"cloud<{self.cloud_max}%"
            )
        return items

    def stream_tile(
        self,
        stac_item,
        row_start: int,
        col_start: int,
        reference_crs: str,
        reference_transform,
    ) -> Optional[np.ndarray]:
        """
        Stream a single 512x512 tile from a STAC item using COG windowed reads.
        Only the bytes for this specific window are downloaded over HTTP.

        Returns np.ndarray of shape (4, 512, 512) — [Red, Green, Blue, NIR]
        Returns None if the tile has excessive nodata.
        """
        _, planetary_computer = _try_import_stac()
        arrays = []

        for band in REQUIRED_BANDS:
            href = stac_item.assets[band].href
            signed_href = planetary_computer.sign(href)

            try:
                with rasterio.open(signed_href) as src:
                    # Build geographic bounds from pixel offsets + reference transform
                    left = reference_transform.c + col_start * reference_transform.a
                    top = reference_transform.f + row_start * reference_transform.e
                    right = left + self.tile_size * reference_transform.a
                    bottom = top + self.tile_size * reference_transform.e

                    # Reproject bounds from reference CRS to source CRS if needed
                    if str(src.crs) != reference_crs:
                        left, bottom, right, top = transform_bounds(
                            reference_crs, str(src.crs),
                            left, bottom, right, top
                        )

                    window = from_bounds(left, bottom, right, top, src.transform)
                    data = src.read(
                        1,
                        window=window,
                        out_shape=(self.tile_size, self.tile_size),
                        resampling=rasterio.enums.Resampling.bilinear,
                    )
                    arrays.append(data.astype(np.float32))

            except Exception as e:
                logger.error(f"Failed to stream band {band}: {e}")
                return None

        tile = np.stack(arrays, axis=0)  # shape: (4, 512, 512)

        # Skip tiles with >30% nodata
        nodata_ratio = np.mean(tile[0] == 0)
        if nodata_ratio > 0.30:
            logger.debug(f"Skipping tile (nodata_ratio={nodata_ratio:.2f})")
            return None

        return tile

    def stream_and_save_tiles(
        self,
        stac_item,
        output_dir: Path,
        reference_crs: str,
        reference_transform,
        scene_width: int,
        scene_height: int,
    ) -> List[Dict]:
        """
        Stream all tiles for a scene and save them to output_dir.
        Returns metadata list for each saved tile.

        Storage: each tile is ~1–3MB. Total for a 10,000x10,000 scene
        at 512px / 20% overlap ≈ 400 tiles ≈ 400–1200MB.
        Call cleanup_tiles() after inference to reclaim this space.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        step = int(self.tile_size * (1 - self.overlap))
        metadata = []
        tile_idx = 0

        for row_start in range(0, scene_height - self.tile_size + 1, step):
            for col_start in range(0, scene_width - self.tile_size + 1, step):
                tile_data = self.stream_tile(
                    stac_item, row_start, col_start,
                    reference_crs, reference_transform
                )
                if tile_data is None:
                    continue

                tile_transform = rasterio.transform.from_origin(
                    reference_transform.c + col_start * reference_transform.a,
                    reference_transform.f + row_start * reference_transform.e,
                    abs(reference_transform.a),
                    abs(reference_transform.e),
                )

                tile_path = output_dir / f"tile_{tile_idx:05d}.tif"
                profile = {
                    "driver": "GTiff", "dtype": "float32",
                    "width": self.tile_size, "height": self.tile_size,
                    "count": 4, "crs": reference_crs,
                    "transform": tile_transform, "compress": "lzw",
                }
                with rasterio.open(tile_path, "w", **profile) as dst:
                    dst.write(tile_data)

                metadata.append({
                    "tile_id": tile_idx,
                    "path": str(tile_path),
                    "row_start": row_start,
                    "col_start": col_start,
                })
                tile_idx += 1
                logger.debug(f"Streamed tile {tile_idx}")

        logger.info(f"Streamed {tile_idx} tiles → {output_dir}")
        return metadata

    def cleanup_tiles(self, tile_dir: Path) -> int:
        """
        Delete all .tif tiles after inference is complete.
        Only the mask PNGs and metadata JSON are kept.
        Returns number of files deleted.
        """
        deleted = 0
        for tif in Path(tile_dir).glob("*.tif"):
            tif.unlink()
            deleted += 1
        logger.info(f"Cleaned up {deleted} tile files from {tile_dir}")
        return deleted
