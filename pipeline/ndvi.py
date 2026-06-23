"""
pipeline/ndvi.py

NDVI (Normalized Difference Vegetation Index) map generation.

Generates a colorized NDVI visualization from Sentinel-2 spectral bands
using the RdYlGn colormap:
    Red    → low vegetation / bare soil / built areas
    Yellow → transitional / sparse vegetation
    Green  → dense, healthy vegetation / cropland
"""

import numpy as np


def generate_ndvi_map_from_bands(
    red: np.ndarray,
    green: np.ndarray,
    blue: np.ndarray,
    nir: np.ndarray,
) -> np.ndarray:
    """
    Generate a colorized NDVI map from Sentinel-2 spectral band arrays.

    NDVI = (NIR - Red) / (NIR + Red)

    The raw NDVI is clipped to [-0.1, 0.8] and normalized before
    applying the RdYlGn matplotlib colormap.

    Args:
        red:   float32 array — Sentinel-2 B04 (Red)
        green: float32 array — Sentinel-2 B03 (Green, unused in NDVI calc)
        blue:  float32 array — Sentinel-2 B02 (Blue, unused in NDVI calc)
        nir:   float32 array — Sentinel-2 B08 (Near-Infrared)

    Returns:
        np.ndarray of shape (H, W, 3), dtype uint8 — RGB NDVI visualization.
    """
    import matplotlib
    import matplotlib.cm as cm  # noqa: F401

    denom = nir + red
    denom[denom == 0] = 1.0        # avoid divide-by-zero
    ndvi = (nir - red) / denom

    ndvi_clipped = np.clip(ndvi, -0.1, 0.8)
    norm_ndvi = (ndvi_clipped - (-0.1)) / (0.8 - (-0.1))

    cmap = matplotlib.colormaps["RdYlGn"]
    ndvi_rgba = (cmap(norm_ndvi) * 255.0).astype(np.uint8)
    return ndvi_rgba[:, :, :3]
