"""
pipeline/zone_pipeline.py

Top-level zone asset generation orchestrator.

``generate_zone_assets()`` is the single public function that drives the
full ETL pipeline for one zone/year combination:

    1. Fetch Sentinel-2 true-color at native resolution (network mode)
    2. Fetch matching ESRI Land Cover tile (network mode)
    3. Generate NDVI map from spectral bands
    4. Fall back to spatially-coherent mock data (mock mode or on failure)
    5. Compute ABI timeseries statistics
    6. Compute encroachment metrics and generate heatmap
    7. Assemble and write verdict.json

All generated assets are saved under ``demo/precomputed/<zone_key>/``.
"""

import json
import logging
from pathlib import Path

import numpy as np
from PIL import Image

from analytics.abi import compute_abi, compute_cropland_loss_ha
from analytics.encroachment import calculate_encroachment_stats, generate_encroachment_heatmap
from analytics.grader import generate_verdict
from core.config import PRECOMPUTED_DIR
from core.image_utils import mask_to_rgb
from pipeline.landcover_fetcher import fetch_esri_landcover_tile
from pipeline.mock_generator import generate_realistic_mock, mask_to_ndvi, mask_to_true_color
from pipeline.ndvi import generate_ndvi_map_from_bands
from pipeline.sentinel_fetcher import fetch_sentinel2_true_color

logger = logging.getLogger(__name__)


import math

def calculate_auto_resolution(bbox: list[float], max_px: int = 1024) -> tuple[int, int] | None:
    """
    Calculate the pixel dimensions required to fetch Sentinel-2 imagery
    at exactly 10 meters per pixel, preserving the aspect ratio.
    If the required resolution is within max_px, returns None (native resolution).
    Otherwise, returns scaled (height, width) tuple capped at max_px.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    # ~111,320 meters per degree latitude
    height_m = (lat_max - lat_min) * 111320
    # meters per degree longitude scales with latitude
    center_lat = (lat_min + lat_max) / 2.0
    width_m = (lon_max - lon_min) * 111320 * math.cos(math.radians(center_lat))

    native_w = max(int(round(width_m / 10.0)), 1)
    native_h = max(int(round(height_m / 10.0)), 1)

    if native_w <= max_px and native_h <= max_px:
        return None

    ratio = min(max_px / native_w, max_px / native_h)
    target_w = max(int(round(native_w * ratio)), 1)
    target_h = max(int(round(native_h * ratio)), 1)
    return (target_h, target_w)


def save_sharp_image(img_arr: np.ndarray, path: Path, min_dim: int = 512, is_mask: bool = False):
    """
    Save a numpy image array to disk. If the image is smaller than min_dim,
    upscale it cleanly to ensure it is sharp in the dashboard.
    """
    img = Image.fromarray(img_arr)
    w, h = img.size
    if w < min_dim or h < min_dim:
        ratio = max(min_dim / w, min_dim / h)
        new_w = max(int(round(w * ratio)), 1)
        new_h = max(int(round(h * ratio)), 1)
        resample = Image.Resampling.NEAREST if is_mask else Image.Resampling.LANCZOS
        img = img.resize((new_w, new_h), resample=resample)
    img.save(path)


def _process_single_year(
    zone_key: str,
    zone_dir: Path,
    bbox: list[float],
    year: int,
    use_network: bool,
) -> tuple[np.ndarray, bool]:
    """
    Fetch or generate all assets for a single year within a zone.

    Returns (farmguard_mask, is_mock) tuple.
    """
    fg_mask: np.ndarray | None = None

    if use_network:
        try:
            is_custom = zone_key.startswith("bbox_")
            output_size = calculate_auto_resolution(bbox) if is_custom else None
            # 1. Fetch Sentinel-2
            tc_rgb, bands = fetch_sentinel2_true_color(bbox, year, output_size=output_size)

            if tc_rgb is not None:
                h, w = tc_rgb.shape[:2]
                logger.info("  Sentinel-2 fetched at size: %dx%d", w, h)
                save_sharp_image(tc_rgb, zone_dir / f"true_color_{year}.png", is_mask=False)

                if bands is not None:
                    red, green, blue, nir = bands
                    ndvi_img = generate_ndvi_map_from_bands(red, green, blue, nir)
                    save_sharp_image(ndvi_img, zone_dir / f"ndvi_map_{year}.png", is_mask=False)

                # 2. Fetch ESRI LC at the same shape
                fg_mask, _ = fetch_esri_landcover_tile(bbox, year, output_shape=(h, w))
            else:
                fallback_shape = 512 if is_custom else 1024
                logger.warning("  Sentinel-2 failed; falling back to %d px for ESRI LC.", fallback_shape)
                fg_mask, _ = fetch_esri_landcover_tile(bbox, year, output_shape=(fallback_shape, fallback_shape))

            if fg_mask is not None:
                logger.info("  ESRI Land Cover fetched for %d", year)
                save_sharp_image(mask_to_rgb(fg_mask), zone_dir / f"mask_rgb_{year}.png", is_mask=True)

        except Exception as exc:
            logger.warning("  Network fetch failed for %s/%d: %s — using mock.", zone_key, year, exc)
            fg_mask = None

    is_mock = False
    # Fall back to mock if network mode produced nothing
    if fg_mask is None:
        size = 1024
        logger.info("  Generating realistic mock for %s — %d…", zone_key, year)
        fg_mask = generate_realistic_mock(zone_key, year, size)
        save_sharp_image(mask_to_rgb(fg_mask), zone_dir / f"mask_rgb_{year}.png", is_mask=True)
        save_sharp_image(mask_to_true_color(fg_mask, size, year), zone_dir / f"true_color_{year}.png", is_mask=False)
        save_sharp_image(mask_to_ndvi(fg_mask, size, year), zone_dir / f"ndvi_map_{year}.png", is_mask=False)
        is_mock = True
    else:
        # Ensure all three visual overlays exist to prevent frontend 404s when switching modes
        h, w = fg_mask.shape[:2]
        tc_path = zone_dir / f"true_color_{year}.png"
        ndvi_path = zone_dir / f"ndvi_map_{year}.png"
        if not tc_path.exists():
            logger.info("  True color image missing; generating mock fallback from mask")
            save_sharp_image(mask_to_true_color(fg_mask, w, year), tc_path, is_mask=False)
            is_mock = True
        if not ndvi_path.exists():
            logger.info("  NDVI image missing; generating mock fallback from mask")
            save_sharp_image(mask_to_ndvi(fg_mask, w, year), ndvi_path, is_mask=False)
            is_mock = True

    return fg_mask, is_mock


def generate_zone_assets(
    zone_key: str,
    bbox: list[float],
    years: list[int],
    use_network: bool = True,
    output_dir: Path = None,
) -> dict:
    """
    Generate and persist all precomputed assets for a geographic zone.

    For each year in *years*:
        - ``true_color_YYYY.png``  — Sentinel-2 true-color composite
        - ``ndvi_map_YYYY.png``    — Colorized NDVI visualization
        - ``mask_rgb_YYYY.png``    — FarmGuard class-color segmentation mask

    Plus zone-level outputs:
        - ``encroachment_heatmap.png`` — full-range encroachment overlay
        - ``verdict.json``             — ABI timeseries + risk verdict

    Args:
        zone_key:    Machine-readable zone identifier (e.g. "nashik_north").
        bbox:        [lon_min, lat_min, lon_max, lat_max] in WGS84.
        years:       Ordered list of years to process.
        use_network: If False, skip STAC API calls and use mock data only.
        output_dir:  Optional custom directory where output assets will be saved.

    Returns:
        The assembled verdict dict (also written to verdict.json).
    """
    zone_dir = output_dir if output_dir is not None else (PRECOMPUTED_DIR / zone_key)
    zone_dir.mkdir(parents=True, exist_ok=True)

    timeseries_stats: list[dict] = []
    masks_by_year: dict[int, np.ndarray] = {}
    is_any_mock = False

    for yr in years:
        logger.info("Processing %s — %d…", zone_key, yr)
        mask, is_mock = _process_single_year(zone_key, zone_dir, bbox, yr, use_network)
        if is_mock:
            is_any_mock = True
        
        # Compute ABI + supplementary percentage stats for this year
        stats = compute_abi(mask)
        stats["year"] = yr
        stats["soil_pixels"] = int((mask == 5).sum())
        stats["soil_pct"] = round(stats["soil_pixels"] / mask.size * 100, 2)
        stats["buildings_pct"] = round(stats["buildings_pixels"] / mask.size * 100, 2)
        stats["vegetation_pct"] = round(stats["vegetation_pixels"] / mask.size * 100, 2)
        stats["water_pct"] = round(stats["water_pixels"] / mask.size * 100, 2)
        stats["cropland_pct"] = round(stats["cropland_pixels"] / mask.size * 100, 2)
        
        masks_by_year[yr] = mask
        timeseries_stats.append(stats)

    timeseries_stats = sorted(timeseries_stats, key=lambda x: x["year"])
    sorted_years = sorted(years)
    first_year_mask = masks_by_year[sorted_years[0]]
    last_year_mask = masks_by_year[sorted_years[-1]]

    # Encroachment analysis — compare first vs last year
    loss_ha = 0.0
    encroachment_stats = {"total_cropland_lost_ha": 0.0, "total_water_lost_ha": 0.0}

    if first_year_mask is not None and last_year_mask is not None:
        loss_ha = compute_cropland_loss_ha(first_year_mask, last_year_mask, resolution_m=10.0)
        encroachment_stats = calculate_encroachment_stats(
            first_year_mask, last_year_mask, mapping_type="esri"
        )
        heatmap_arr = generate_encroachment_heatmap(
            first_year_mask, last_year_mask, mapping_type="esri"
        )
        heatmap_path = zone_dir / "encroachment_heatmap.png"
        save_sharp_image(heatmap_arr, heatmap_path, is_mask=True)
        logger.info("  Saved encroachment heatmap → %s", heatmap_path)

    verdict = generate_verdict(timeseries_stats, zone_key, cropland_loss_ha=loss_ha)
    verdict["encroachment"] = encroachment_stats
    verdict["is_mock"] = is_any_mock

    verdict_path = zone_dir / "verdict.json"
    with open(verdict_path, "w") as fh:
        json.dump(verdict, fh, indent=2)
 
    logger.info(
        "  Grade %s  (ABI=%.3f, Crop loss=%.1f ha, Encroachment=%.1f ha)",
        verdict["grade"], verdict["abi"], loss_ha,
        encroachment_stats["total_cropland_lost_ha"],
    )
    return verdict
