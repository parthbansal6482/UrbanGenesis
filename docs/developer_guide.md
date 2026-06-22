# Developer Guide — FarmGuard

This document provides developer guidelines, environment setup instructions, and reference documentation for the FarmGuard backend REST APIs.

---

## 1. Environment & Config Variables

Configure these settings inside the root `.env` file:

| Variable | Scope | Purpose | Default Value |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | Frontend | Target URL of the running FastAPI backend service. | `http://localhost:8000` |
| `CORS_ORIGINS` | Backend | Comma-separated list of origins permitted to make CORS requests. | `http://localhost:3000,http://127.0.0.1:3000` |
| `UVICORN_RELOAD` | Backend | Enables hot-reloading for local uvicorn development when set to `true`. | `false` |
| `GEMINI_API_KEY` | Backend | API Key used by U-Net prototype forecasts or automated analytics helpers. | *None* |

---

## 2. API Reference

### A. Fetch Registered Farmland Zones
* **URL**: `/api/zones`
* **Method**: `GET`
* **Headers**: `Cache-Control: public, max-age=300`
* **Response**:
  ```json
  [
    {
      "key": "nashik_north",
      "name": "Nashik North Agricultural Zone",
      "bbox": [73.72, 20.05, 73.98, 20.25],
      "center": [20.15, 73.85],
      "years": [2017, 2019, 2021, 2023, 2025],
      "satyukt_relevance": "Grape and onion belt. Sat4Risk flood zone. MRV baseline.",
      "latest_grade": "A",
      "latest_abi": 6.4025,
      "overall_abi_change_pct": -51.4,
      "cropland_loss_ha": 5497.24,
      "encroachment_alert": true
    }
  ]
  ```

### B. Run Regional Comparison Analysis
* **URL**: `/api/analyse`
* **Method**: `GET`
* **Parameters**:
  - `zone` (str, Required): Registered region key (e.g. `bengaluru`). Checked to prevent directory traversal.
  - `before` (int, Optional): Starting comparison year. Defaults to oldest available year.
  - `after` (int, Optional): Ending comparison year. Defaults to latest available year.
* **Response**:
  ```json
  {
    "zone_info": {
      "key": "bengaluru",
      "name": "Bengaluru Agricultural Buffer Zone",
      "bbox": [77.45, 12.83, 77.75, 13.1],
      "center": [12.965, 77.6],
      "years": [2017, 2019, 2021, 2023, 2025],
      "satyukt_relevance": "Satyukt headquarters regional cropland buffer tracker."
    },
    "metrics": {
      "latest_abi": 0.1241,
      "overall_abi_change_pct": -44.4,
      "cropland_loss_ha": 9435.52,
      "grade": "F",
      "label": "Critical — Encroachment Alert",
      "description": "Severe urban encroachment. Cropland loss quantified.",
      "encroachment_alert": true,
      "encroachment": {
        "total_cropland_lost_ha": 4120.4,
        "total_water_lost_ha": 145.6
      }
    },
    "comparison": {
      "before_year": 2017,
      "after_year": 2025,
      "before_abi": 0.2234,
      "after_abi": 0.1241,
      "abi_change_pct": -44.4
    },
    "transitions": [
      { "class_id": 1, "class_name": "Buildings", "before_pct": 72.16, "after_pct": 79.02, "trend_shift_pct": 6.86, "status": "increase" },
      { "class_id": 2, "class_name": "Cropland", "before_pct": 12.67, "after_pct": 3.17, "trend_shift_pct": -9.5, "status": "decrease" }
    ],
    "timeseries": [
      {
        "year": 2017,
        "abi": 0.2234,
        "cropland_pixels": 1258456,
        "vegetation_pixels": 199815,
        "water_pixels": 142751,
        "buildings_pixels": 7167929,
        "soil_pixels": 1164360,
        "cropland_pct": 12.67,
        "vegetation_pct": 2.01,
        "water_pct": 1.44,
        "buildings_pct": 72.16,
        "soil_pct": 11.72,
        "encroach_pct": 72.16
      }
    ],
    "overlays": {
      "before": { "true_color": "/static/bengaluru/true_color_2017.png", "ndvi": "/static/bengaluru/ndvi_map_2017.png", "mask": "/static/bengaluru/mask_rgb_2017.png" },
      "after": { "true_color": "/static/bengaluru/true_color_2023.png", "ndvi": "/static/bengaluru/ndvi_map_2023.png", "mask": "/static/bengaluru/mask_rgb_2023.png" },
      "encroachment_heatmap": "/static/bengaluru/encroachment_heatmap_2017_2025.png"
    }
  }
  ```

---

## 3. Development Workflow

### Data Ingestion (ETL)
Generate the precomputed native-resolution assets for registered agricultural zones:
```bash
python scripts/fetch_esri_landcover.py --zone all
```

### Run Backend Server (FastAPI)
```bash
UVICORN_RELOAD=true PYTHONPATH=. python app.py
```

### Run Frontend Client (Next.js)
```bash
cd dashboard
npm install
npm run dev
```

### Verify Codebase (pytest)
```bash
PYTHONPATH=. pytest tests/ -v
```
