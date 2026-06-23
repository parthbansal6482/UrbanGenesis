"""
pipeline/landcover_fetcher.py

Fetches ESRI Annual Land Cover (io-lulc-annual-v02) tiles from
Microsoft Planetary Computer and remaps them to the FarmGuard 6-class schema.

Available years: 2017–2023 (clamped automatically for years outside range).

ESRI → FarmGuard remapping is applied here — downstream analytics only
ever see FarmGuard class IDs.
"""

import logging

import numpy as np

from core.class_map import ESRI_TO_FARMGUARD
from pipeline.stac_client import create_stac_client

# Set GDAL environment variables before rasterio is imported at call time
import os
os.environ.setdefault("GDAL_HTTP_TIMEOUT", "300")
os.environ.setdefault("GDAL_HTTP_CONNECTTIMEOUT", "60")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "3")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

logger = logging.getLogger(__name__)

_ESRI_COLLECTION = "io-lulc-annual-v02"
_ESRI_YEAR_MIN = 2017
_ESRI_YEAR_MAX = 2023


def fetch_esri_landcover_tile(
    bbox: list[float],
    year: int,
    output_shape: int | tuple[int, int] = 1024,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """
    Fetch ESRI Annual Land Cover for a bounding box and year.

    Multi-tile mosaicking is applied automatically: the first non-zero ESRI
    class value wins at each pixel, so overlapping tile edges are handled
    gracefully.

    Args:
        bbox:         [lon_min, lat_min, lon_max, lat_max] in WGS84 (EPSG:4326).
        year:         Target year. Clamped to [2017, 2023] if out of range.
        output_shape: Output pixel dimensions. Pass an int for a square output
                      or a (height, width) tuple.

    Returns:
        (farmguard_mask, esri_mask) as uint8 numpy arrays of the requested shape,
        or (None, None) if no tiles are found or all reads fail.
    """
    try:
        import planetary_computer
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import transform_bounds
        from rasterio.windows import from_bounds
    except ImportError:
        raise ImportError("Required: pip install pystac-client planetary-computer rasterio")

    if isinstance(output_shape, int):
        out_h, out_w = output_shape, output_shape
    else:
        out_h, out_w = output_shape

    # Clamp to the available ESRI LC year range
    esri_year = min(max(year, _ESRI_YEAR_MIN), _ESRI_YEAR_MAX)
    if year != esri_year:
        logger.warning("ESRI LC not available for %d, using %d", year, esri_year)

    client = create_stac_client()

    search = client.search(
        collections=[_ESRI_COLLECTION],
        bbox=bbox,
        datetime=f"{esri_year}-01-01/{esri_year}-12-31",
        max_items=10,
    )
    items = list(search.items())

    if not items:
        logger.warning("No ESRI LC items found for bbox=%s, year=%d", bbox, esri_year)
        return None, None

    logger.info("Found %d ESRI LC tiles for %d", len(items), esri_year)

    lon_min, lat_min, lon_max, lat_max = bbox
    all_tiles: list[np.ndarray] = []

    for item in items:
        href = item.assets["data"].href
        try:
            signed_href = planetary_computer.sign(href)
            with rasterio.open(signed_href) as src:
                src_crs = src.crs
                if src_crs and str(src_crs).upper() not in ("EPSG:4326", "CRS84"):
                    left, bottom, right, top = transform_bounds(
                        "EPSG:4326", src_crs, lon_min, lat_min, lon_max, lat_max
                    )
                else:
                    left, bottom, right, top = lon_min, lat_min, lon_max, lat_max

                window = from_bounds(left, bottom, right, top, src.transform)
                data = src.read(
                    1,
                    window=window,
                    out_shape=(out_h, out_w),
                    resampling=Resampling.nearest,
                    boundless=True,
                    fill_value=0,
                )
                all_tiles.append(data)
        except Exception as exc:
            logger.warning("Failed to read ESRI LC tile: %s", exc)
            continue

    if not all_tiles:
        return None, None

    # Mosaic: first non-zero value wins
    esri_mask = np.zeros((out_h, out_w), dtype=np.uint8)
    for tile in all_tiles:
        valid = (tile > 0) & (esri_mask == 0)
        esri_mask[valid] = tile[valid]

    # Remap ESRI classes → FarmGuard classes
    farmguard_mask = np.zeros_like(esri_mask)
    for esri_cls, fg_cls in ESRI_TO_FARMGUARD.items():
        farmguard_mask[esri_mask == esri_cls] = fg_cls

    return farmguard_mask, esri_mask
