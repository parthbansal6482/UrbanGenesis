# Developer Guide — FarmGuard

This document provides developer guidelines, environment setup instructions, REST API reference, and operational procedures for the FarmGuard backend and frontend.

---

## 1. Environment & Config Variables

Configure these settings inside the root `.env` file (copy from `.env.example`):

| Variable | Scope | Purpose | Default |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | Frontend | Target URL of the running FastAPI backend. | `http://localhost:8000` |
| `CORS_ORIGINS` | Backend | Comma-separated list of origins permitted to make CORS requests. | `http://localhost:3000,http://127.0.0.1:3000` |
| `UVICORN_RELOAD` | Backend | Enables hot-reloading for local uvicorn development when set to `true`. | `false` |
| `GEMINI_API_KEY` | Backend | API Key for automated analytics helpers. | *None* |
| `PC_SDK_SUBSCRIPTION_KEY` | Backend / ETL | Optional Planetary Computer subscription key. Anonymous access (without a key) works fine for most STAC queries but may have lower rate limits. | *None* |

---

## 2. Registered Zones

There are **14 registered zones** defined in `config/settings.yaml`:

| Zone Key | Region | Notes |
|---|---|---|
| `nashik_north` | Maharashtra | Grape and onion belt; Sat4Risk flood zone; MRV baseline |
| `vijayawada_west` | Andhra Pradesh | Krishna delta agricultural corridor |
| `hubli_outskirts` | Karnataka | Peri-urban farmland fringe |
| `bengaluru` | Karnataka | Satyukt HQ regional cropland buffer tracker |
| `pune_east` | Maharashtra | Rapidly urbanising Deccan fringe |
| `jaipur_south` | Rajasthan | Semi-arid agricultural zone |
| `ludhiana_rural` | Punjab | Wheat belt — high-value cropland |
| `coimbatore_north` | Tamil Nadu | Cotton and sugarcane zone |
| `patna_west` | Bihar | Indo-Gangetic plain paddy zone |
| `indore_peripheral` | Madhya Pradesh | Soybean belt peri-urban fringe |
| `guwahati_east` | Assam | Tea and paddy corridor |
| `hyderabad_west` | Telangana | Cotton and horticulture zone |
| `lucknow_outer` | Uttar Pradesh | Sugarcane and paddy outer ring |
| `nagpur_rural` | Maharashtra | Vidarbha cotton and orange grove belt |

---

## 3. API Reference

### A. Fetch Registered Farmland Zones

- **URL**: `GET /api/zones`
- **Parameters**:
  - `format` (str, optional): `list` (default) returns an array; `object` returns a dictionary keyed by zone key.
- **Headers**: `Cache-Control: public, max-age=300`
- **Response (default list format)**:
  ```json
  [
    {
      "key": "nashik_north",
      "name": "Nashik North Agricultural Zone",
      "bbox": [73.72, 20.05, 73.98, 20.25],
      "center": [20.15, 73.85],
      "years": [2017, 2019, 2021, 2023],
      "satyukt_relevance": "Grape and onion belt. Sat4Risk flood zone. MRV baseline.",
      "latest_grade": "A",
      "latest_abi": 6.4025,
      "overall_abi_change_pct": -51.4,
      "cropland_loss_ha": 5497.24,
      "encroachment_alert": true
    }
  ]
  ```

---

### B. Run Regional Comparison Analysis

- **URL**: `GET /api/analyse`
- **Parameters**:
  - `zone` (str, required): Registered region key (e.g. `bengaluru`). Validated against the allowed zones list to prevent directory traversal.
  - `before` (int, optional): Starting comparison year. Defaults to oldest available year.
  - `after` (int, optional): Ending comparison year. Defaults to latest available year.
- **Response**:
  ```json
  {
    "zone_info": {
      "key": "bengaluru",
      "name": "Bengaluru Agricultural Buffer Zone",
      "bbox": [77.45, 12.83, 77.75, 13.1],
      "center": [12.965, 77.6],
      "years": [2017, 2019, 2021, 2023],
      "satyukt_relevance": "Satyukt headquarters regional cropland buffer tracker."
    },
    "metrics": {
      "latest_abi": 0.1241,
      "overall_abi_change_pct": -44.4,
      "cropland_loss_ha": 9435.52,
      "grade": "F",
      "label": "Critical — Encroachment Alert",
      "encroachment_alert": true,
      "encroachment": {
        "total_cropland_lost_ha": 4120.4,
        "total_water_lost_ha": 145.6
      }
    },
    "comparison": {
      "before_year": 2017,
      "after_year": 2023,
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
      "before": {
        "true_color": "/static/bengaluru/true_color_2017.png",
        "ndvi": "/static/bengaluru/ndvi_map_2017.png",
        "mask": "/static/bengaluru/mask_rgb_2017.png"
      },
      "after": {
        "true_color": "/static/bengaluru/true_color_2023.png",
        "ndvi": "/static/bengaluru/ndvi_map_2023.png",
        "mask": "/static/bengaluru/mask_rgb_2023.png"
      },
      "encroachment_heatmap": "/static/bengaluru/encroachment_heatmap_2017_2023.png"
    }
  }
  ```

---

### C. Run Custom Bounding Box Analysis

Runs on-demand ETL ingestion, LULC class conversion, and ABI computation for any custom geographic bounding box.

- **URL**: `POST /api/analyse_bbox`
- **Headers**: `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "min_lon": 73.72,
    "min_lat": 20.05,
    "max_lon": 73.98,
    "max_lat": 20.25,
    "years": [2017, 2019, 2021, 2023],
    "force_refresh": false
  }
  ```
  - `min_lon` / `min_lat` / `max_lon` / `max_lat` (float, required): Bounding box in WGS84. Area must not exceed `0.25` deg² (~50km × 50km).
  - `years` (list of int, optional): Custom timeline years list.
  - `force_refresh` (bool, optional): Set `true` to bypass backend cache and regenerate Sentinel-2/LULC layers.
- **Response**: Returns a JSON payload with the schema of `/api/analyse` (including `"is_mock": true/false`), with overlay paths pointing to `/static_custom/{cache_key}/{filename}`.
- **Caching**: Results are cached under `demo/custom_cache/{cache_key}/`.

---

### D. Trigger U-Net Forecast for a Zone

Runs the recursive U-Net inference pipeline for a registered zone or custom region, projecting land-cover forward to a target year. Architecture is auto-detected from checkpoint keys.

- **URL**: `POST /api/forecast_bbox`
- **Headers**: `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "zone_key": "bengaluru",
    "start_year": 2023,
    "target_year": 2041
  }
  ```
  - `zone_key` (str, required): A registered zone key from `config/settings.yaml`.
  - `start_year` (int, required): The most recent historical year to begin recursion from.
  - `target_year` (int, required): The year to forecast forward to (maximum 2041).
- **Behaviour**: Loads `model/checkpoints/unet_weights.pt` via `load_model_from_checkpoint()` (which auto-detects UNet vs. ResNet34UNet from the state_dict). Runs recursive 2-year-step inference from `start_year` to `target_year`. Saves predicted mask PNGs alongside precomputed assets and returns the extended timeseries including all forecast years.
- **Response**:
  ```json
  {
    "zone_key": "bengaluru",
    "forecast_years": [2025, 2027, 2029, 2031, 2033, 2035, 2037, 2039, 2041],
    "timeseries": [ ... ],
    "overlays": { ... }
  }
  ```

---

### E. Delete Custom Bbox Cache

Deletes precomputed disk assets and cache folder for a custom bounding box.

- **URL**: `DELETE /api/analyse_bbox/{cache_key}`
- **Parameters**:
  - `cache_key` (str, required): Key of custom region to delete (must start with `bbox_` prefix).
- **Response**:
  ```json
  {
    "status": "success",
    "message": "Successfully deleted custom data for bbox_73.72_20.05_73.98_20.25"
  }
  ```

---

### F. Fetch Custom Region Static Overlay

- **URL**: `GET /static_custom/{cache_key}/{filename}`
- **Parameters**:
  - `cache_key` (str, required): Coordinate-derived cache key for the region.
  - `filename` (str, required): Asset file name (e.g. `true_color_2023.png`, `ndvi_map_2023.png`, `mask_rgb_2023.png`, `encroachment_heatmap.png`).
- **Response**: Binary image data stream (`image/png`).

---

## 4. Development Workflow

### Data Ingestion (ETL) — `precompute.py`

Generate the precomputed native-resolution assets for registered agricultural zones:

```bash
# All zones, live satellite data
python precompute.py

# Single named zone
python precompute.py --zone bengaluru

# Offline synthetic mock data (no network required)
python precompute.py --mock

# Run full U-Net recursive forecast to 2041 after ETL
python precompute.py --forecast
```

> **Note**: `PC_SDK_SUBSCRIPTION_KEY` in `.env` is optional. Anonymous Planetary Computer access is available by default.

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

### TypeScript Type-Check

```bash
cd dashboard && npx tsc --noEmit
```

### Frontend Linting

```bash
cd dashboard && npm run lint
```

### Verify Codebase (pytest)

Run the full test suite (44 passing tests):

```bash
PYTHONPATH=. pytest tests/ -v
```

### Backtest U-Net Forecasting Model

Compares historical 2021 training cutoffs against real 2023 ground-truth outcomes:

```bash
PYTHONPATH=. python model/backtest.py
```

This computes Pixel Accuracy and ABI Prediction Error, generating comparison overlays under `backtest_results/`.

---

## 5. Model Architecture Auto-Detection

`model/forecast.py` exports `load_model_from_checkpoint(checkpoint_path)`, which inspects the saved state_dict keys to determine which architecture was used during training:

- If `input_projection.weight` is present in the state_dict → loads **`ResNet34UNet`** (pretrained ResNet34 backbone).
- Otherwise → loads standard **`UNet`** (from-scratch, 22-channel input).

This makes the checkpoint format self-describing — no manual architecture flag is required.

---

## 6. Model Stress Testing

The `scripts/model_stress_test.py` script provides a comprehensive, automated 4-suite model audit. Run with:

```bash
PYTHONPATH=. .venv/bin/python scripts/model_stress_test.py --report <output.md>
```

Replace `<output.md>` with the desired report output path (e.g. `model_audit_report.md`).

### Suite 1 — Historical Backtesting

Evaluates model accuracy against real ESRI LULC ground truth across two historical intervals (`2019→2021` and `2021→2023`):

- **Metrics**: Pixel Accuracy, Macro-mIoU (mean Intersection over Union across all 6 classes), and ABI Prediction Error.
- **Latest audit results (2021→2023 interval)**:

  | Zone | Pixel Accuracy | Macro-mIoU | ABI Error |
  |---|---|---|---|
  | Bengaluru | 91.30% | 60.74% | 13.0% |
  | Hubli Outskirts | 91.42% | 74.83% | 8.9% |
  | Nashik North | 92.12% | 67.74% | 5.4% |
  | Vijayawada West | 89.55% | 75.64% | 5.1% |

### Suite 2 — Physical Transition Constraint Integrity

Verifies that no physically banned transitions appear in the model's predicted outputs:

- Checks include: Buildings → Cropland, Buildings → Water, Water → Buildings (instantaneous), and other disallowed state changes.
- **Finding**: Violation rates of **0.5–1.5%** detected on legacy precomputed assets (generated before the hard constraint was applied); **0.00%** on live inference with the current constraint enforcement.

### Suite 3 — Long-Horizon Stability

Runs recursive U-Net prediction to **2035** and measures for degenerate output patterns:

- Checks: vanishing cropland (total cropland → 0), exploding sprawl (buildings coverage > 95%), or class collapse (single class dominates).
- **Finding**: All 4 monitored zones remain stable to 2035 with no degenerate collapse detected.

### Suite 4 — OSM Road Sensitivity

Measures the delta in building-class prediction probability when the road network input is zeroed out:

- Quantifies how much the OSM corridor magnetism bias affects the output.
- **Finding**: Road sensitivity (prediction shift) of **0.00–0.03%** across all zones — indicating OSM bias is applied correctly but is not the dominant driver of prediction.

---

## 7. Validation Numbers Summary

The following table consolidates the full backtest results from `scripts/model_stress_test.py` across both evaluation intervals:

| Zone | Interval | Pixel Accuracy | ABI Error | Macro-mIoU |
|---|---|---|---|---|
| Bengaluru | 2019→2021 | 90.83% | 16.5% | — |
| Bengaluru | 2021→2023 | 91.30% | 13.0% | 60.74% |
| Hubli Outskirts | 2019→2021 | 88.96% | 8.7% | — |
| Hubli Outskirts | 2021→2023 | 91.42% | 8.9% | 74.83% |
| Nashik North | 2019→2021 | 94.64% | 1.0% | — |
| Nashik North | 2021→2023 | 92.12% | 5.4% | 67.74% |
| Vijayawada West | 2019→2021 | 88.07% | 19.3% | — |
| Vijayawada West | 2021→2023 | 89.55% | 5.1% | 75.64% |

> [!NOTE]
> Macro-mIoU is only reported for the `2021→2023` interval (the primary validation interval). The `2019→2021` interval uses an earlier version of the evaluation harness that did not compute mIoU.
