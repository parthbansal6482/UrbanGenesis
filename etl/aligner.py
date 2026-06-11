"""
etl/aligner.py

Reprojects all input GeoTIFFs to a common CRS and snaps them to the same
pixel grid so that multi-year images line up pixel-for-pixel.
"""

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

TARGET_CRS = "EPSG:32643"   # UTM Zone 43N — covers peninsular India (Nashik, Vijayawada, Hubli, Bengaluru)
TARGET_RESOLUTION = 10.0    # metres, matching Sentinel-2 10m bands

def align_to_reference(
    source_path: Path,
    reference_path: Path,
    output_path: Path,
) -> Path:
    """
    Reproject source raster to exactly match the CRS, transform, and dimensions
    of the reference raster. This guarantees pixel-for-pixel alignment.
    """
    with rasterio.open(reference_path) as ref:
        ref_crs = ref.crs
        ref_transform = ref.transform
        ref_width = ref.width
        ref_height = ref.height

    with rasterio.open(source_path) as src:
        data_shape = (src.count, ref_height, ref_width)
        profile = src.profile.copy()

    profile.update({
        "crs": ref_crs,
        "transform": ref_transform,
        "width": ref_width,
        "height": ref_height,
        "driver": "GTiff",
        "compress": "lzw",          # Lossless compression — critical for scientific data
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
    })

    reprojected = np.zeros(data_shape, dtype=profile["dtype"])

    with rasterio.open(source_path) as src:
        for band_idx in range(1, src.count + 1):
            reproject(
                source=rasterio.band(src, band_idx),
                destination=reprojected[band_idx - 1],
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=ref_transform,
                dst_crs=ref_crs,
                resampling=Resampling.bilinear,   # Bilinear for continuous data
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(reprojected)

    logger.info(f"Aligned {source_path.name} → {output_path}")
    return output_path


def stack_bands(band_paths: dict, output_path: Path) -> Path:
    """
    Stack individual band GeoTIFFs (B04, B03, B02, B08) into a single
    4-channel GeoTIFF. Band order: [Red, Green, Blue, NIR].
    """
    band_order = ["B04", "B03", "B02", "B08"]
    arrays = []

    with rasterio.open(band_paths[band_order[0]]) as ref:
        profile = ref.profile.copy()
        profile.update(count=4, driver="GTiff", compress="lzw",
                       tiled=True, blockxsize=512, blockysize=512)

    for band in band_order:
        with rasterio.open(band_paths[band]) as src:
            arrays.append(src.read(1))

    stacked = np.stack(arrays, axis=0)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(stacked)

    logger.info(f"Stacked bands {band_order} into {output_path}")
    return output_path
