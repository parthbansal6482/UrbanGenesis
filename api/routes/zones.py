"""
api/routes/zones.py

GET /api/zones

Returns a JSON array of all configured geographic zones along with their
latest analytical summary metrics (grade, ABI, cropland loss, alert flag).
Responses are cached by the browser for 5 minutes via Cache-Control headers.
"""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.dependencies import get_zones_config, load_zone_verdict

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/zones")
def get_zones(format: str = "list") -> JSONResponse:
    """
    List all configured agricultural zones with summary metrics.

    Each entry includes:
        key                  — machine-readable zone identifier
        name                 — human-readable zone name
        bbox                 — [lon_min, lat_min, lon_max, lat_max] (WGS84)
        center               — [lat, lon] centroid
        years                — available timeseries years
        satyukt_relevance    — commercial context note
        latest_grade         — A–F risk grade derived from latest ABI
        latest_abi           — Agricultural Buffer Index (latest year)
        overall_abi_change_pct — % ABI change from first to latest year
        cropland_loss_ha     — total cropland lost to encroachment (ha)
        encroachment_alert   — True if rapid ABI drop detected in timeseries
    """
    zones_config = get_zones_config()
    zones_list = []

    for key, val in zones_config.items():
        bbox = val.get("bbox", [0.0, 0.0, 0.0, 0.0])
        center = [(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2]

        # Defaults — used when no precomputed verdict is available
        latest_grade = "N/A"
        latest_abi = 0.0
        overall_abi_change_pct = 0.0
        cropland_loss_ha = 0.0
        encroachment_alert = False

        verdict = load_zone_verdict(key)
        if verdict:
            latest_grade = verdict.get("grade", "N/A")
            latest_abi = verdict.get("abi", 0.0)
            overall_abi_change_pct = verdict.get("overall_abi_change_pct", 0.0)
            cropland_loss_ha = verdict.get("cropland_loss_ha", 0.0)
            encroachment_alert = verdict.get("encroachment_alert", False)

        zones_list.append({
            "key": key,
            "name": val.get("name", key),
            "bbox": bbox,
            "center": center,
            "years": val.get("years", [2017, 2019, 2021, 2023, 2025]),
            "satyukt_relevance": val.get("satyukt_relevance", ""),
            "latest_grade": latest_grade,
            "latest_abi": latest_abi,
            "overall_abi_change_pct": overall_abi_change_pct,
            "cropland_loss_ha": cropland_loss_ha,
            "encroachment_alert": encroachment_alert,
        })

    if format == "object":
        return JSONResponse(
            content={
                "zones": zones_list,
                "custom_region_supported": True,
                "custom_region_constraints": {
                    "max_area_deg2": 0.25,
                    "min_area_deg2": 0.0001,
                }
            },
            headers={"Cache-Control": "public, max-age=300"},
        )

    return JSONResponse(
        content=zones_list,
        headers={"Cache-Control": "public, max-age=300"},
    )
