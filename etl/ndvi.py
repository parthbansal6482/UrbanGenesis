"""
etl/ndvi.py

Computes NDVI and a binary vegetation mask from a stacked 4-band GeoTIFF.
Band order expected: [Red=0, Green=1, Blue=2, NIR=3] (rasterio bands 1 and 4)
"""

import numpy as np
import rasterio
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

NDVI_VEGETATION_THRESHOLD = 0.3


def compute_ndvi(stacked_tif: Path, output_path: Path) -> np.ndarray:
    """
    NDVI = (NIR - Red) / (NIR + Red)
    Values range from -1 to 1.
    Pixels > 0.3 are healthy vegetation.
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

    # Make sure there are no NaN values
    ndvi = np.nan_to_num(ndvi, nan=0.0, posinf=1.0, neginf=-1.0)

    profile.update(count=1, dtype="float32", compress="lzw", tiled=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(ndvi[np.newaxis, :, :])

    vegetation_mask = (ndvi > NDVI_VEGETATION_THRESHOLD).astype(np.uint8)
    logger.info(f"NDVI computed. Vegetation coverage: {vegetation_mask.mean()*100:.1f}%")
    return ndvi
