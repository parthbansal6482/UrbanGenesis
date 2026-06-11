"""
etl/vegetation.py

Computes vegetation metrics from a stacked 4-band GeoTIFF.
Band order expected: [Red=0, Green=1, Blue=2, NIR=3] (rasterio bands 1 and 4)

Provides two metrics:
  - NDVI: standard normalised difference vegetation index, range [-1, 1]
  - cropland_fraction: fraction of pixels classified as cropland (class 3)
    from a segmentation mask, range [0, 1]
"""

import numpy as np
import rasterio
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

NDVI_VEGETATION_THRESHOLD = 0.3
CROPLAND_CLASS = 3


def compute_ndvi(stacked_tif: Path, output_path: Path) -> np.ndarray:
    """
    NDVI = (NIR - Red) / (NIR + Red)
    Values range from -1 to 1.
    Pixels > 0.3 are healthy vegetation.

    Args:
        stacked_tif: Path to 4-band stacked GeoTIFF (Red, Green, Blue, NIR)
        output_path: Path to write float32 NDVI GeoTIFF

    Returns:
        ndvi: np.ndarray of shape (H, W), values in [-1, 1]
    """
    with rasterio.open(stacked_tif) as src:
        red = src.read(1).astype(np.float32)
        nir = src.read(4).astype(np.float32)
        profile = src.profile.copy()

    # Avoid division by zero and invalid value warnings
    denominator = nir + red
    with np.errstate(divide='ignore', invalid='ignore'):
        ndvi = (nir - red) / (denominator + 1e-8)
        ndvi = np.where(denominator <= 1e-8, 0.0, ndvi)

    ndvi = np.clip(ndvi, -1.0, 1.0)
    ndvi = np.nan_to_num(ndvi, nan=0.0, posinf=1.0, neginf=-1.0)

    profile.update(count=1, dtype="float32", compress="lzw", tiled=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(ndvi[np.newaxis, :, :])

    vegetation_mask = (ndvi > NDVI_VEGETATION_THRESHOLD).astype(np.uint8)
    logger.info(f"NDVI computed. Vegetation coverage: {vegetation_mask.mean()*100:.1f}%")
    return ndvi


def compute_cropland_fraction(
    mask: np.ndarray,
    cropland_class: int = CROPLAND_CLASS,
) -> float:
    """
    Compute the fraction of pixels in a segmentation mask classified as cropland.

    Args:
        mask: np.ndarray of shape (H, W) with integer class IDs
        cropland_class: class index for cropland (default: 3, per FarmGuard class map)

    Returns:
        float in [0.0, 1.0] — proportion of pixels that are cropland
    """
    total_pixels = mask.size
    if total_pixels == 0:
        return 0.0
    cropland_pixels = int((mask == cropland_class).sum())
    fraction = cropland_pixels / total_pixels
    logger.debug(
        f"Cropland fraction: {fraction:.4f} "
        f"({cropland_pixels}/{total_pixels} pixels)"
    )
    return float(fraction)
