"""
etl/tiler.py

Splits a large GeoTIFF scene into overlapping 512x512 tiles.
Each tile is saved with its geographic metadata preserved so results
can be stitched back into a full-scene map after inference.

tile_size and overlap are sourced from config["tiling"]["tile_size"] and
config["tiling"]["overlap"] — see config/settings.yaml.
"""

import numpy as np
import rasterio
from rasterio.windows import Window
from pathlib import Path
import json
import logging

logger = logging.getLogger(__name__)


def generate_tiles(
    scene_path: Path,
    output_dir: Path,
    tile_size: int = 512,
    overlap: float = 0.20,
    min_valid_ratio: float = 0.70,
) -> list:
    """
    Generates overlapping tiles from a large scene GeoTIFF.
    Returns list of metadata dicts for each saved tile.

    Optimisation: uses rasterio windowed reading — never loads the full
    scene into memory at once.
    """
    step = int(tile_size * (1 - overlap))
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_list = []

    with rasterio.open(scene_path) as src:
        scene_width = src.width
        scene_height = src.height
        scene_transform = src.transform
        scene_crs = str(src.crs)
        nodata = src.nodata if src.nodata is not None else 0

        # Adjust dimensions if the scene is smaller than tile_size
        effective_tile_height = min(tile_size, scene_height)
        effective_tile_width = min(tile_size, scene_width)

        # Handle rows and columns
        row_ranges = range(0, max(1, scene_height - effective_tile_height + 1), step)
        col_ranges = range(0, max(1, scene_width - effective_tile_width + 1), step)

        tile_idx = 0
        for row_start in row_ranges:
            for col_start in col_ranges:
                # Adjust window size if it goes out of bounds (should not with above ranges, but to be safe)
                w_width = min(effective_tile_width, scene_width - col_start)
                w_height = min(effective_tile_height, scene_height - row_start)
                
                window = Window(col_start, row_start, w_width, w_height)
                tile_data = src.read(window=window)

                # Skip tiles with too many nodata pixels
                valid_ratio = np.mean(tile_data[0] != nodata)
                if valid_ratio < min_valid_ratio:
                    continue

                # Derive tile geotransform
                tile_transform = rasterio.windows.transform(window, scene_transform)

                tile_filename = f"tile_{tile_idx:05d}_r{row_start}_c{col_start}.tif"
                tile_path = output_dir / tile_filename

                tile_profile = {
                    "driver": "GTiff",
                    "dtype": tile_data.dtype,
                    "width": w_width,
                    "height": w_height,
                    "count": tile_data.shape[0],
                    "crs": scene_crs,
                    "transform": tile_transform,
                    "compress": "lzw",
                }

                with rasterio.open(tile_path, "w", **tile_profile) as dst:
                    dst.write(tile_data)

                metadata_list.append({
                    "tile_id": tile_idx,
                    "path": str(tile_path),
                    "row_start": row_start,
                    "col_start": col_start,
                    "width": w_width,
                    "height": w_height,
                    "transform": list(tile_transform),
                    "crs": scene_crs,
                    "valid_ratio": float(valid_ratio),
                })
                tile_idx += 1

    meta_path = output_dir / "tiles_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata_list, f, indent=2)

    logger.info(f"Generated {tile_idx} tiles from {scene_path.name}")
    return metadata_list
