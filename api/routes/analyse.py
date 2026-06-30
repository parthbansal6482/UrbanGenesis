"""
api/routes/analyse.py

GET /api/analyse

Detailed zone analysis endpoint. Accepts optional `before` and `after` year
query parameters to drive side-by-side comparisons.

Responsibilities:
    - Validate zone key against configuration whitelist
    - Load or synthesize a fallback verdict for zones with no precomputed data
    - Compute dynamic ABI change, grade, and transition stats for the
      requested year window
    - Generate (or serve from cache) a per-window encroachment heatmap
    - Return all overlay URLs, metrics, transitions, and timeseries
"""

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.bbox_utils import InvalidBBoxError, bbox_cache_key
from pipeline.custom_region_pipeline import CUSTOM_REGION_CACHE_DIR, get_cached_or_analyse

from analytics.grader import assign_grade
from api.dependencies import get_zones_config, load_zone_verdict
from core.config import PRECOMPUTED_DIR
from core.image_utils import rgb_to_mask

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fallback_verdict(zone: str, zone_cfg: dict) -> dict:
    """
    Synthesize a deterministic placeholder verdict when verdict.json is absent.

    Returns a plausible declining ABI trajectory so the UI renders
    meaningfully even without precomputed satellite data on disk.
    """
    years = zone_cfg.get("years", [2017, 2019, 2021, 2023, 2025])
    timeseries = []
    for idx, yr in enumerate(years):
        abi_val = max(1.5 - idx * 0.3, 0.2)
        b_pct = idx * 10.0 + 5.0
        c_pct = max(60.0 - idx * 12.0, 10.0)
        v_pct = 15.0
        w_pct = 5.0
        s_pct = 100.0 - (b_pct + c_pct + v_pct + w_pct)
        timeseries.append({
            "year": yr,
            "abi": abi_val,
            "cropland_pixels": int(c_pct * 100_000),
            "vegetation_pixels": int(v_pct * 100_000),
            "water_pixels": int(w_pct * 100_000),
            "buildings_pixels": int(b_pct * 100_000),
            "soil_pixels": int(s_pct * 100_000),
            "cropland_pct": c_pct,
            "vegetation_pct": v_pct,
            "water_pct": w_pct,
            "buildings_pct": b_pct,
            "soil_pct": s_pct,
        })
    return {
        "zone": zone,
        "latest_year": years[-1],
        "abi": timeseries[-1]["abi"],
        "grade": "D",
        "label": "Elevated Risk",
        "description": "Simulation placeholder data — verdict.json missing on disk.",
        "overall_abi_change_pct": -50.0,
        "cropland_loss_ha": 1200.0,
        "encroachment_alert": True,
        "timeseries": timeseries,
    }


def _get_overlay_url(zone: str, filename: str) -> Optional[str]:
    """Return the static URL for a precomputed asset file, or None if absent."""
    if (PRECOMPUTED_DIR / zone / filename).exists():
        return f"/static/{zone}/{filename}"
    return None


def _build_transitions(rec_before: Optional[dict], rec_after: Optional[dict]) -> list:
    """
    Build a per-class transition list comparing land-cover percentages
    between two timeseries records.
    """
    classes_to_compare = [
        (1, "Buildings",        "buildings_pct"),
        (2, "Cropland",         "cropland_pct"),
        (3, "Dense Vegetation", "vegetation_pct"),
        (4, "Water Bodies",     "water_pct"),
        (5, "Bare Soil",        "soil_pct"),
    ]
    transitions = []
    for class_id, label, field in classes_to_compare:
        pct_before = rec_before.get(field, 0.0) if rec_before else 0.0
        pct_after = rec_after.get(field, 0.0) if rec_after else 0.0
        diff = pct_after - pct_before
        status = "increase" if diff > 0.05 else ("decrease" if diff < -0.05 else "stable")
        transitions.append({
            "class_id": class_id,
            "class_name": label,
            "before_pct": pct_before,
            "after_pct": pct_after,
            "trend_shift_pct": diff,
            "status": status,
        })
    return transitions


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/api/analyse")
def analyse_zone(
    zone: str = Query(..., description="Zone key to analyze"),
    before: Optional[int] = Query(None, description="Start year for comparison"),
    after: Optional[int] = Query(None, description="End year for comparison"),
):
    """
    Detailed analysis for a single agricultural zone.

    Returns:
        zone_info      — key, name, bbox, center, years, relevance note
        metrics        — latest ABI, grade, cropland loss (ha), encroachment stats
        comparison     — before/after years and their ABI values + % change
        transitions    — per-class land-cover shifts (%)
        timeseries     — full yearly ABI + pixel-count records
        overlays       — URLs for true-color, NDVI, mask, and heatmap images
    """
    zones_config = get_zones_config()

    if zone not in zones_config:
        raise HTTPException(status_code=404, detail=f"Zone '{zone}' not found in configuration.")

    zone_cfg = zones_config[zone]
    verdict = load_zone_verdict(zone) or _fallback_verdict(zone, zone_cfg)

    timeseries = verdict.get("timeseries", [])
    available_years = sorted(r["year"] for r in timeseries)

    if not available_years:
        raise HTTPException(status_code=500, detail="No timeseries data found for this zone.")

    # Resolve before/after years — fall back to first/last if not specified or invalid
    before_yr = before if before in available_years else available_years[0]
    after_yr = after if after in available_years else available_years[-1]

    if before_yr > after_yr:
        logger.warning(
            "Zone '%s': before_yr (%d) > after_yr (%d), swapping silently.",
            zone, before_yr, after_yr,
        )
        before_yr, after_yr = after_yr, before_yr

    rec_before = next((r for r in timeseries if r["year"] == before_yr), None)
    rec_after = next((r for r in timeseries if r["year"] == after_yr), None)

    # ABI metrics
    before_abi = rec_before.get("abi", 0.0) if rec_before else 0.0
    after_abi = rec_after.get("abi", 0.0) if rec_after else 0.0
    abi_change_pct = round(((after_abi - before_abi) / before_abi) * 100.0, 1) if before_abi > 0 else 0.0

    grade_info = assign_grade(after_abi)

    # Dynamic cropland loss estimate from pixel counts
    if rec_before and rec_after:
        dynamic_crop_loss_ha = round(
            (rec_before.get("cropland_pixels", 0) - rec_after.get("cropland_pixels", 0)) * 0.01, 2
        )
    else:
        dynamic_crop_loss_ha = verdict.get("cropland_loss_ha", 0.0)

    # Encroachment stats and heatmap
    encroachment_stats = {"total_cropland_lost_ha": 0.0, "total_water_lost_ha": 0.0}
    encroachment_heatmap_url: Optional[str] = None

    before_mask_path = PRECOMPUTED_DIR / zone / f"mask_rgb_{before_yr}.png"
    after_mask_path = PRECOMPUTED_DIR / zone / f"mask_rgb_{after_yr}.png"

    if before_mask_path.exists() and after_mask_path.exists():
        try:
            from PIL import Image
            from analytics.encroachment import calculate_encroachment_stats, generate_encroachment_heatmap

            mask_before = rgb_to_mask(np.array(Image.open(before_mask_path).convert("RGB")))
            mask_after = rgb_to_mask(np.array(Image.open(after_mask_path).convert("RGB")))

            encroachment_stats = calculate_encroachment_stats(
                mask_before, mask_after, mapping_type="esri"
            )

            heatmap_filename = f"encroachment_heatmap_{before_yr}_{after_yr}.png"
            heatmap_path = PRECOMPUTED_DIR / zone / heatmap_filename
            if not heatmap_path.exists():
                heatmap_arr = generate_encroachment_heatmap(
                    mask_before, mask_after, mapping_type="esri"
                )
                Image.fromarray(heatmap_arr).save(heatmap_path)

            encroachment_heatmap_url = f"/static/{zone}/{heatmap_filename}"

        except Exception as exc:
            logger.error("Error computing encroachment for zone %s: %s", zone, exc)

    # Fall back to the precomputed all-years heatmap
    if not encroachment_heatmap_url:
        encroachment_heatmap_url = _get_overlay_url(zone, "encroachment_heatmap.png")
        encroachment_stats = verdict.get("encroachment", encroachment_stats)

    bbox = zone_cfg.get("bbox", [0.0, 0.0, 0.0, 0.0])
    center = [(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2]

    return {
        "zone_info": {
            "key": zone,
            "name": zone_cfg.get("name", zone),
            "bbox": bbox,
            "center": center,
            "years": available_years,
            "satyukt_relevance": zone_cfg.get("satyukt_relevance", ""),
        },
        "metrics": {
            "latest_abi": after_abi,
            "overall_abi_change_pct": abi_change_pct,
            "cropland_loss_ha": dynamic_crop_loss_ha,
            "grade": grade_info.get("grade", "N/A"),
            "label": grade_info.get("label", ""),
            "description": grade_info.get("description", ""),
            "encroachment_alert": verdict.get("encroachment_alert", False),
            "encroachment": encroachment_stats,
        },
        "comparison": {
            "before_year": before_yr,
            "after_year": after_yr,
            "before_abi": before_abi,
            "after_abi": after_abi,
            "abi_change_pct": abi_change_pct,
        },
        "transitions": _build_transitions(rec_before, rec_after),
        "timeseries": timeseries,
        "overlays": {
            "before": {
                "true_color": _get_overlay_url(zone, f"true_color_{before_yr}.png"),
                "ndvi": _get_overlay_url(zone, f"ndvi_map_{before_yr}.png"),
                "mask": _get_overlay_url(zone, f"mask_rgb_{before_yr}.png"),
            },
            "after": {
                "true_color": _get_overlay_url(zone, f"true_color_{after_yr}.png"),
                "ndvi": _get_overlay_url(zone, f"ndvi_map_{after_yr}.png"),
                "mask": _get_overlay_url(zone, f"mask_rgb_{after_yr}.png"),
            },
            "encroachment_heatmap": encroachment_heatmap_url,
        },
    }


class BBoxAnalyseRequest(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    years: list[int] | None = None
    force_refresh: bool | None = False


@router.post("/api/analyse_bbox")
def analyse_bbox(request: BBoxAnalyseRequest):
    bbox = (request.min_lon, request.min_lat, request.max_lon, request.max_lat)
    try:
        target_years = [2017, 2019, 2021, 2023]
        if request.force_refresh:
            import shutil
            cache_key = bbox_cache_key(bbox)
            cache_dir = CUSTOM_REGION_CACHE_DIR / cache_key
            if cache_dir.exists():
                logger.info(f"Force refresh requested for bbox {bbox} — deleting cached folder {cache_dir}")
                shutil.rmtree(cache_dir)

        verdict = get_cached_or_analyse(bbox, years=target_years)
        cache_key = bbox_cache_key(bbox)

        # Build the exact same output structure as analyse_zone
        timeseries = verdict.get("timeseries", [])
        available_years = sorted(r["year"] for r in timeseries)

        if not available_years:
            raise HTTPException(status_code=500, detail="No timeseries data found.")

        # Clamp requested years to available generated years to prevent returning URLs for non-existent years
        requested_before = request.years[0] if (request.years and len(request.years) > 0) else available_years[0]
        requested_after = request.years[-1] if (request.years and len(request.years) > 1) else available_years[-1]

        before_yr = min(available_years, key=lambda x: abs(x - requested_before))
        after_yr = min(available_years, key=lambda x: abs(x - requested_after))

        rec_before = next((r for r in timeseries if r["year"] == before_yr), None)
        rec_after = next((r for r in timeseries if r["year"] == after_yr), None)

        before_abi = rec_before.get("abi", 0.0) if rec_before else 0.0
        after_abi = rec_after.get("abi", 0.0) if rec_after else 0.0
        abi_change_pct = round(((after_abi - before_abi) / before_abi) * 100.0, 1) if before_abi > 0 else 0.0

        grade_info = assign_grade(after_abi)

        if rec_before and rec_after:
            dynamic_crop_loss_ha = round(
                (rec_before.get("cropland_pixels", 0) - rec_after.get("cropland_pixels", 0)) * 0.01, 2
            )
        else:
            dynamic_crop_loss_ha = verdict.get("cropland_loss_ha", 0.0)

        encroachment_stats = verdict.get("encroachment", {"total_cropland_lost_ha": 0.0, "total_water_lost_ha": 0.0})

        return {
            "zone_info": {
                "key": cache_key,
                "name": f"Custom Region ({bbox[0]:.3f}, {bbox[1]:.3f})",
                "bbox": list(bbox),
                "center": [(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2],
                "years": available_years,
                "satyukt_relevance": "User drawn arbitrary region analysis.",
            },
            "metrics": {
                "latest_abi": after_abi,
                "overall_abi_change_pct": abi_change_pct,
                "cropland_loss_ha": dynamic_crop_loss_ha,
                "grade": grade_info.get("grade", "N/A"),
                "label": grade_info.get("label", ""),
                "description": grade_info.get("description", ""),
                "encroachment_alert": verdict.get("encroachment_alert", False),
                "encroachment": encroachment_stats,
            },
            "comparison": {
                "before_year": before_yr,
                "after_year": after_yr,
                "before_abi": before_abi,
                "after_abi": after_abi,
                "abi_change_pct": abi_change_pct,
            },
            "transitions": _build_transitions(rec_before, rec_after),
            "timeseries": timeseries,
            "overlays": {
                "before": {
                    "true_color": f"/static_custom/{cache_key}/true_color_{before_yr}.png",
                    "ndvi": f"/static_custom/{cache_key}/ndvi_map_{before_yr}.png",
                    "mask": f"/static_custom/{cache_key}/mask_rgb_{before_yr}.png",
                },
                "after": {
                    "true_color": f"/static_custom/{cache_key}/true_color_{after_yr}.png",
                    "ndvi": f"/static_custom/{cache_key}/ndvi_map_{after_yr}.png",
                    "mask": f"/static_custom/{cache_key}/mask_rgb_{after_yr}.png",
                },
                "encroachment_heatmap": f"/static_custom/{cache_key}/encroachment_heatmap.png",
            },
        }
    except InvalidBBoxError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Custom analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/static_custom/{cache_key}/{filename}")
def serve_custom_file(cache_key: str, filename: str):
    file_path = CUSTOM_REGION_CACHE_DIR / cache_key / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)
