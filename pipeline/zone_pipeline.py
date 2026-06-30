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


def _process_single_year(
    zone_key: str,
    zone_dir: Path,
    bbox: list[float],
    year: int,
    use_network: bool,
) -> np.ndarray:
    """
    Fetch or generate all assets for a single year within a zone.

    Returns the FarmGuard class-ID mask (uint8 ndarray) for the year.
    """
    fg_mask: np.ndarray | None = None

    if use_network:
        try:
            is_custom = zone_key.startswith("bbox_")
            output_size = 512 if is_custom else None
            # 1. Fetch Sentinel-2
            tc_rgb, bands = fetch_sentinel2_true_color(bbox, year, output_size=output_size)

            if tc_rgb is not None:
                h, w = tc_rgb.shape[:2]
                logger.info("  Sentinel-2 fetched at size: %dx%d", w, h)
                Image.fromarray(tc_rgb).save(zone_dir / f"true_color_{year}.png")

                if bands is not None:
                    red, green, blue, nir = bands
                    ndvi_img = generate_ndvi_map_from_bands(red, green, blue, nir)
                    Image.fromarray(ndvi_img).save(zone_dir / f"ndvi_map_{year}.png")

                # 2. Fetch ESRI LC at the same shape
                fg_mask, _ = fetch_esri_landcover_tile(bbox, year, output_shape=(h, w))
            else:
                fallback_shape = 512 if is_custom else 1024
                logger.warning("  Sentinel-2 failed; falling back to %d px for ESRI LC.", fallback_shape)
                fg_mask, _ = fetch_esri_landcover_tile(bbox, year, output_shape=(fallback_shape, fallback_shape))

            if fg_mask is not None:
                logger.info("  ESRI Land Cover fetched for %d", year)
                Image.fromarray(mask_to_rgb(fg_mask)).save(zone_dir / f"mask_rgb_{year}.png")

        except Exception as exc:
            logger.warning("  Network fetch failed for %s/%d: %s — using mock.", zone_key, year, exc)
            fg_mask = None

    # Fall back to mock if network mode produced nothing
    if fg_mask is None:
        size = 1024
        logger.info("  Generating realistic mock for %s — %d…", zone_key, year)
        fg_mask = generate_realistic_mock(zone_key, year, size)
        Image.fromarray(mask_to_rgb(fg_mask)).save(zone_dir / f"mask_rgb_{year}.png")
        Image.fromarray(mask_to_true_color(fg_mask, size, year)).save(zone_dir / f"true_color_{year}.png")
        Image.fromarray(mask_to_ndvi(fg_mask, size, year)).save(zone_dir / f"ndvi_map_{year}.png")
    else:
        # Ensure all three visual overlays exist to prevent frontend 404s when switching modes
        h, w = fg_mask.shape[:2]
        tc_path = zone_dir / f"true_color_{year}.png"
        ndvi_path = zone_dir / f"ndvi_map_{year}.png"
        if not tc_path.exists():
            logger.info("  True color image missing; generating mock fallback from mask")
            Image.fromarray(mask_to_true_color(fg_mask, w, year)).save(tc_path)
        if not ndvi_path.exists():
            logger.info("  NDVI image missing; generating mock fallback from mask")
            Image.fromarray(mask_to_ndvi(fg_mask, w, year)).save(ndvi_path)

    return fg_mask


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

    for yr in years:
        logger.info("Processing %s — %d…", zone_key, yr)
        mask = _process_single_year(zone_key, zone_dir, bbox, yr, use_network)
        
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
        Image.fromarray(heatmap_arr).save(heatmap_path)
        logger.info("  Saved encroachment heatmap → %s", heatmap_path)

    verdict = generate_verdict(timeseries_stats, zone_key, cropland_loss_ha=loss_ha)
    verdict["encroachment"] = encroachment_stats

    verdict_path = zone_dir / "verdict.json"
    with open(verdict_path, "w") as fh:
        json.dump(verdict, fh, indent=2)
 
    logger.info(
        "  Grade %s  (ABI=%.3f, Crop loss=%.1f ha, Encroachment=%.1f ha)",
        verdict["grade"], verdict["abi"], loss_ha,
        encroachment_stats["total_cropland_lost_ha"],
    )
    return verdict
