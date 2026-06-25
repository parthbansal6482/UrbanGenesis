"""
pipeline/custom_region_pipeline.py

On-demand analysis entry point for arbitrary bounding boxes.
Reuses the exact same fetch/NDVI/ABI/encroachment logic as zone_pipeline.py,
but runs synchronously for a single user-supplied bbox instead of a
pre-configured named zone, and does not require a year list ahead of time —
it defaults to the most recent available imagery plus one historical
comparison year.
"""

import logging
from pathlib import Path
from typing import Dict, Tuple

from core.bbox_utils import bbox_cache_key, validate_bbox
from pipeline.zone_pipeline import generate_zone_assets

logger = logging.getLogger(__name__)

CUSTOM_REGION_CACHE_DIR = Path("demo/custom_cache")
DEFAULT_COMPARISON_YEARS = [2019, 2023]  # sensible default for now


def analyse_custom_bbox(
    bbox: Tuple[float, float, float, float],
    years: list = None,
) -> Dict:
    """
    Runs the full FarmGuard analysis pipeline for an arbitrary bbox.
    Returns the same verdict structure as the named-zone path.

    This function does NOT precompute and store permanently — results
    are cached under demo/custom_cache/<cache_key>/ and may be evicted
    or refreshed, unlike the curated demo/precomputed/ zones.
    """
    bbox = validate_bbox(bbox)
    years = years or DEFAULT_COMPARISON_YEARS
    cache_key = bbox_cache_key(bbox)
    region_dir = CUSTOM_REGION_CACHE_DIR / cache_key
    region_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Running custom-region analysis for bbox={bbox}, years={years}")

    # Check if satellite data is available for the bbox
    try:
        from pipeline.stac_client import create_stac_client
        client = create_stac_client()
        search = client.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime="2023-01-01/2023-12-31",
            max_items=1,
        )
        items = list(search.item_collection())
        if not items:
            raise ValueError(
                f"Satellite or land-cover data is not available for this region. "
                f"This can happen in areas with no recent cloud-free imagery, "
                f"or regions outside current ESRI LULC coverage. Try a nearby region."
            )
    except ValueError:
        raise
    except Exception as e:
        logger.warning(f"Could not verify STAC data availability (possibly offline): {e}")

    try:
        assets = generate_zone_assets(
            zone_key=cache_key,
            bbox=list(bbox),
            output_dir=region_dir,
            years=years,
        )
    except Exception as e:
        logger.error(f"Data unavailable for bbox {bbox}: {e}")
        raise ValueError(
            f"Satellite or land-cover data is not available for this region. "
            f"This can happen in areas with no recent cloud-free imagery, "
            f"or regions outside current ESRI LULC coverage. Try a nearby region."
        )

    return assets


def get_cached_or_analyse(bbox: Tuple[float, float, float, float], years: list = None) -> Dict:
    """
    Checks for a cached result first. If found and not stale, returns it.
    Otherwise runs the full analysis and caches the result.
    """
    bbox = validate_bbox(bbox)
    cache_key = bbox_cache_key(bbox)
    verdict_path = CUSTOM_REGION_CACHE_DIR / cache_key / "verdict.json"

    if verdict_path.exists():
        import json

        logger.info(f"Cache hit for {cache_key}")
        with open(verdict_path) as f:
            return json.load(f)

    logger.info(f"Cache miss for {cache_key} — running fresh analysis")
    return analyse_custom_bbox(bbox, years)
