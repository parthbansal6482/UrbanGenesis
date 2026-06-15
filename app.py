import os
import json
import math
import logging
import yaml
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("UrbanGenesisAPI")

# Paths
BASE_DIR = Path(__file__).parent
PRECOMPUTED_DIR = BASE_DIR / "demo" / "precomputed"
CONFIG_PATH = BASE_DIR / "config" / "settings.yaml"

# Load settings
try:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    ZONES_CONFIG = config.get("zones", {})
except Exception as e:
    logger.error(f"Failed to load config/settings.yaml: {e}")
    ZONES_CONFIG = {
        "nashik_north": {
            "name": "Nashik North Agricultural Zone",
            "bbox": [73.72, 20.05, 73.98, 20.25],
            "years": [2017, 2019, 2021, 2023, 2025],
            "satyukt_relevance": "Grape and onion belt. Sat4Risk flood zone. MRV baseline."
        },
        "vijayawada_west": {
            "name": "Vijayawada West Farmland",
            "bbox": [80.45, 16.45, 80.70, 16.65],
            "years": [2017, 2019, 2021, 2023, 2025],
            "satyukt_relevance": "Krishna delta cropland. Insurance client region."
        },
        "hubli_outskirts": {
            "name": "Hubli Peripheral Agricultural Zone",
            "bbox": [74.95, 15.28, 75.20, 15.48],
            "years": [2017, 2019, 2021, 2023, 2025],
            "satyukt_relevance": "Karnataka agri zone. Satyukt active partner region."
        },
        "bengaluru": {
            "name": "Bengaluru Agricultural Buffer Zone",
            "bbox": [77.45, 12.83, 77.75, 13.10],
            "years": [2017, 2019, 2021, 2023, 2025],
            "satyukt_relevance": "Satyukt headquarters regional cropland buffer tracker."
        }
    }

# Canonical Class Information
CLASS_INFO = {
    0: {"name": "Background", "color": "#000000", "emoji": "⬛"},
    1: {"name": "Buildings", "color": "#DC2626", "emoji": "🏢"},
    2: {"name": "Cropland", "color": "#D4A017", "emoji": "🌾"},
    3: {"name": "Dense Vegetation", "color": "#228B22", "emoji": "🌳"},
    4: {"name": "Water Bodies", "color": "#1E64C8", "emoji": "💧"},
    5: {"name": "Bare Soil", "color": "#D2B48C", "emoji": "🏜️"},
}

app = FastAPI(
    title="UrbanGenesis API",
    description="Backend API for Satyukt Farmland Encroachment Detection System",
    version="1.0.0"
)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount precomputed directory under /static
if PRECOMPUTED_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(PRECOMPUTED_DIR)), name="static")
    logger.info(f"Mounted static directory: {PRECOMPUTED_DIR}")
else:
    logger.warning(f"Precomputed directory does not exist at: {PRECOMPUTED_DIR}")

def safe_float(v, default=0.0):
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default

def load_zone_verdict(zone_key: str) -> Optional[dict]:
    verdict_path = PRECOMPUTED_DIR / zone_key / "verdict.json"
    if not verdict_path.exists():
        return None
    try:
        with open(verdict_path, "r") as f:
            raw = f.read()
        raw = raw.replace(": Infinity", ": null").replace(":Infinity", ":null")
        raw = raw.replace(": NaN", ": null").replace(":NaN", ":null")
        data = json.loads(raw)
        
        # Sanitise top-level numeric fields
        data["abi"] = safe_float(data.get("abi"), 0.0)
        data["overall_abi_change_pct"] = safe_float(data.get("overall_abi_change_pct"), 0.0)
        data["cropland_loss_ha"] = safe_float(data.get("cropland_loss_ha"), 0.0)
        
        # Sanitise timeseries
        if "timeseries" in data:
            for rec in data["timeseries"]:
                rec["abi"] = safe_float(rec.get("abi"), 0.0)
                rec["cropland_pixels"] = int(rec.get("cropland_pixels", 0))
                rec["vegetation_pixels"] = int(rec.get("vegetation_pixels", 0))
                rec["water_pixels"] = int(rec.get("water_pixels", 0))
                rec["buildings_pixels"] = int(rec.get("buildings_pixels", 0))
                rec["soil_pixels"] = int(rec.get("soil_pixels", 0))
                rec["cropland_pct"] = safe_float(rec.get("cropland_pct"), 0.0)
                rec["vegetation_pct"] = safe_float(rec.get("vegetation_pct"), 0.0)
                rec["water_pct"] = safe_float(rec.get("water_pct"), 0.0)
                rec["buildings_pct"] = safe_float(rec.get("buildings_pct"), 0.0)
                rec["soil_pct"] = safe_float(rec.get("soil_pct"), 0.0)
        return data
    except Exception as e:
        logger.error(f"Error loading verdict.json for zone {zone_key}: {e}")
        return None

@app.get("/api/zones")
def get_zones():
    zones_list = []
    for key, val in ZONES_CONFIG.items():
        bbox = val.get("bbox", [0.0, 0.0, 0.0, 0.0])
        # Center: [lat, lon]
        center = [(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2]
        
        # Default stats if verdict is missing
        latest_grade = "N/A"
        latest_abi = 0.0
        overall_abi_change_pct = 0.0
        cropland_loss_ha = 0.0
        encroachment_alert = False
        
        # Try loading precomputed verdict to get latest stats
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
            "encroachment_alert": encroachment_alert
        })
    return zones_list

@app.get("/api/analyse")
def analyse_zone(
    zone: str = Query(..., description="Key of the zone to analyze"),
    before: Optional[int] = Query(None, description="Start year"),
    after: Optional[int] = Query(None, description="End year")
):
    if zone not in ZONES_CONFIG:
        raise HTTPException(status_code=404, detail=f"Zone '{zone}' not found in configuration.")

    zone_cfg = ZONES_CONFIG[zone]
    verdict = load_zone_verdict(zone)

    if not verdict:
        # Fallback dummy verdict data
        years = zone_cfg.get("years", [2017, 2019, 2021, 2023, 2025])
        timeseries = []
        for idx, yr in enumerate(years):
            abi_val = max(1.5 - (idx * 0.3), 0.2)
            b_pct = idx * 10.0 + 5.0
            c_pct = max(60.0 - idx * 12.0, 10.0)
            v_pct = 15.0
            w_pct = 5.0
            s_pct = 100.0 - (b_pct + c_pct + v_pct + w_pct)
            timeseries.append({
                "year": yr,
                "abi": abi_val,
                "cropland_pixels": int(c_pct * 1000),
                "vegetation_pixels": int(v_pct * 1000),
                "water_pixels": int(w_pct * 1000),
                "buildings_pixels": int(b_pct * 1000),
                "soil_pixels": int(s_pct * 1000),
                "cropland_pct": c_pct,
                "vegetation_pct": v_pct,
                "water_pct": w_pct,
                "buildings_pct": b_pct,
                "soil_pct": s_pct
            })
        verdict = {
            "zone": zone,
            "latest_year": years[-1],
            "abi": timeseries[-1]["abi"],
            "grade": "D",
            "label": "Elevated Risk",
            "description": "Simulation placeholder data since verdict.json is missing on disk.",
            "overall_abi_change_pct": -50.0,
            "cropland_loss_ha": 1200.0,
            "encroachment_alert": True,
            "timeseries": timeseries
        }

    timeseries = verdict.get("timeseries", [])
    available_years = sorted([r["year"] for r in timeseries])

    if not available_years:
        raise HTTPException(status_code=500, detail="No timeseries data found for this zone.")

    # Determine before and after years
    before_yr = before if before in available_years else available_years[0]
    after_yr = after if after in available_years else available_years[-1]

    if before_yr > after_yr:
        before_yr, after_yr = after_yr, before_yr

    rec_before = next((r for r in timeseries if r["year"] == before_yr), None)
    rec_after = next((r for r in timeseries if r["year"] == after_yr), None)

    # Build transition comparisons
    transitions = []
    classes_to_compare = [
        (1, "Buildings", "buildings_pct"),
        (2, "Cropland", "cropland_pct"),
        (3, "Dense Vegetation", "vegetation_pct"),
        (4, "Water Bodies", "water_pct"),
        (5, "Bare Soil", "soil_pct"),
    ]

    for class_id, label, field in classes_to_compare:
        pct_before = rec_before.get(field, 0.0) if rec_before else 0.0
        pct_after = rec_after.get(field, 0.0) if rec_after else 0.0
        diff = pct_after - pct_before
        
        if diff > 0.05:
            status = "increase"
        elif diff < -0.05:
            status = "decrease"
        else:
            status = "stable"
            
        transitions.append({
            "class_id": class_id,
            "class_name": label,
            "before_pct": pct_before,
            "after_pct": pct_after,
            "trend_shift_pct": diff,
            "status": status
        })

    # Prepare overlays paths
    # Helper to check file existence
    def get_overlay_url(filename: str) -> Optional[str]:
        filepath = PRECOMPUTED_DIR / zone / filename
        if filepath.exists():
            return f"/static/{zone}/{filename}"
        return None

    # Before year overlays
    before_tc = get_overlay_url(f"true_color_{before_yr}.png")
    before_ndvi = get_overlay_url(f"ndvi_map_{before_yr}.png")
    before_mask = get_overlay_url(f"mask_rgb_{before_yr}.png")

    # After year overlays
    after_tc = get_overlay_url(f"true_color_{after_yr}.png")
    after_ndvi = get_overlay_url(f"ndvi_map_{after_yr}.png")
    after_mask = get_overlay_url(f"mask_rgb_{after_yr}.png")

    # Bounding box and center
    bbox = zone_cfg.get("bbox", [0.0, 0.0, 0.0, 0.0])
    center = [(bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2]

    return {
        "zone_info": {
            "key": zone,
            "name": zone_cfg.get("name", zone),
            "bbox": bbox,
            "center": center,
            "years": available_years,
            "satyukt_relevance": zone_cfg.get("satyukt_relevance", "")
        },
        "metrics": {
            "latest_abi": verdict.get("abi", 0.0),
            "overall_abi_change_pct": verdict.get("overall_abi_change_pct", 0.0),
            "cropland_loss_ha": verdict.get("cropland_loss_ha", 0.0),
            "grade": verdict.get("grade", "N/A"),
            "label": verdict.get("label", ""),
            "description": verdict.get("description", ""),
            "encroachment_alert": verdict.get("encroachment_alert", False)
        },
        "comparison": {
            "before_year": before_yr,
            "after_year": after_yr,
            "before_abi": rec_before.get("abi", 0.0) if rec_before else 0.0,
            "after_abi": rec_after.get("abi", 0.0) if rec_after else 0.0,
            "abi_change_pct": (((rec_after.get("abi", 0.0) - rec_before.get("abi", 0.0)) / rec_before.get("abi", 1.0) * 100.0) if rec_before and rec_before.get("abi", 0.0) > 0 else 0.0)
        },
        "transitions": transitions,
        "timeseries": timeseries,
        "overlays": {
            "before": {
                "true_color": before_tc,
                "ndvi": before_ndvi,
                "mask": before_mask
            },
            "after": {
                "true_color": after_tc,
                "ndvi": after_ndvi,
                "mask": after_mask
            }
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
