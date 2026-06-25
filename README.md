# FarmGuard — Farmland Encroachment & Risk Analytics Platform

Satyukt-aligned Farmland Encroachment Detection System. Rebuilt from UrbanGenesis to track agricultural boundaries, monitor urban sprawl, and calculate the **Agricultural Buffer Index (ABI)** for Sat4Risk flood indexing, crop insurance premium adjustments, and MRV carbon credit baselines.

---

## 🌟 Key Features
- **Cloud-Composite ESRI Land Cover**: Uses the global 10m cloud-free ESRI LULC annual dataset via Planetary Computer STAC.
- **Native 10m/pixel Spatial Resolution**: Processes high-resolution satellite bands and classification masks at native 10m scale.
- **Multi-Stage Date Fallback Search**: Dynamic Sentinel-2 acquisition search window (Strict February -> Jan 15 - Mar 15 -> Full year fallback) to ensure cloud-free 100% spatial coverage.
- **Agricultural Buffer Index (ABI)**: Computes the ratio of natural buffer to urban infrastructure:
  $$ABI = \frac{\text{Cropland} + \text{Dense Vegetation} + \text{Water Bodies}}{\text{Buildings}}$$
  Handles zero-building zones gracefully by capping ABI at `99.99` to ensure JSON compatibility and correct risk grading.
- **Crop Loss Quantification**: Tracks absolute hectares of cropland converted to built-up area over time.
- **Satyukt Risk Grader**: Converts historical ABI timeseries into risk tiers (Grades A-F) and triggers rapid encroachment alerts.
- **Decoupled Full-Stack Design**: Decoupled Next.js 16 Dashboard and FastAPI Backend with dynamic environment variable support.

---

## 📂 Project Directory Structure
```
FarmGuard/
├── core/                      # Shared constants and utilities (no internal deps)
│   ├── class_map.py           # CLASS_INFO, CLASS_RGB, CLASS_COLORS, ESRI_TO_FARMGUARD
│   ├── config.py              # load_config(), PRECOMPUTED_DIR, safe_float()
│   └── image_utils.py         # rgb_to_mask(), mask_to_rgb()
├── api/                       # FastAPI HTTP layer
│   ├── main.py                # create_app() — CORS, middleware, static mount, routers
│   ├── dependencies.py        # load_zone_verdict() (LRU-cached), get_zones_config()
│   └── routes/
│       ├── zones.py           # GET /api/zones
│       └── analyse.py         # GET /api/analyse
├── pipeline/                  # ETL / data acquisition layer
│   ├── stac_client.py         # authenticated STAC client factory
│   ├── landcover_fetcher.py   # fetch_esri_landcover_tile()
│   ├── sentinel_fetcher.py    # fetch_sentinel2_true_color()
│   ├── ndvi.py                # generate_ndvi_map_from_bands()
│   ├── mock_generator.py      # generate_realistic_mock(), mask_to_true_color()
│   └── zone_pipeline.py       # generate_zone_assets() — full orchestrator
├── analytics/                 # Pure computation — no file I/O
│   ├── __init__.py
│   ├── abi.py                 # ABI calculations and buffer indices
│   ├── change_detection.py    # Transition matrix calculation engine
│   ├── encroachment.py        # calculate_encroachment_stats(), generate_encroachment_heatmap()
│   └── grader.py              # Satyukt risk grader and alert metrics
├── tests/
│   ├── test_analytics.py      # Python tests for analytical functions and math
│   ├── test_api.py            # API client routing integration tests
│   └── test_encroachment.py   # Pixel-level encroachment verification tests
├── config/
│   └── settings.yaml          # Farmland zones, LULC colors, and grading thresholds
├── dashboard/                 # Next.js 16 Dashboard client
├── demo/
│   └── precomputed/           # Precomputed native-res regional files for offline dashboard
├── docs/                      # Architectural and specification documentation
│   ├── architecture.md        # Architecture topology and data flows
│   ├── platform_specification.md # Sat4Risk / MRV / LULC classes specification
│   └── developer_guide.md     # API reference and developer configuration guide
├── app.py                     # Thin shim FastAPI backend server
├── run_pipeline.py            # CLI entrypoint for the ETL pipeline
├── requirements.txt           # Python backend dependencies
└── README.md                  # This file
```

---

## 🚀 Quick Start

### 1. Install Dependencies
Ensure you have Python 3.11+ and Node 20+.
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and configure:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

### 3. Run Ingestion Pipeline (ETL)
Generate the precomputed native-resolution assets for registered agricultural zones.

**Using live satellite data (requires network):**
```bash
python run_pipeline.py
```

**Using local synthetic mock data (no network needed):**
```bash
python run_pipeline.py --mock
```

*Whitelisted zones include: `nashik_north`, `vijayawada_west`, `hubli_outskirts`, `bengaluru`*

### 4. Start Backend Service
```bash
UVICORN_RELOAD=true PYTHONPATH=. python app.py
```

### 5. Start Frontend Dashboard
```bash
cd dashboard
npm install
npm run dev
```
Open `http://localhost:3000` to interact with the platform.

---

## 🧪 Running Verification Tests
Execute the pytest suite to verify math logic, bounds capping, and API response shapes:
```bash
PYTHONPATH=. pytest tests/ -v
```

---

## 📚 Detailed Documentation
For further details, refer to the documents in the `docs/` folder:
- See [docs/architecture.md](file:///Users/parthbansal/Projects/UrbanGenesis/docs/architecture.md) for data flows, sequencing, and component interactions.
- See [docs/platform_specification.md](file:///Users/parthbansal/Projects/UrbanGenesis/docs/platform_specification.md) for Satyukt Sat4Risk/MRV business cases and math index derivations.
- See [docs/developer_guide.md](file:///Users/parthbansal/Projects/UrbanGenesis/docs/developer_guide.md) for environment configuration matrices and REST endpoints.

---

## Custom Region Support — Known Limitations

FarmGuard supports analysis of any user-specified bounding box, subject to:
- **Maximum area**: ~50km x 50km per request (prevents accidental city-or-state-scale requests that would be too slow/expensive to process)
- **Data availability**: regions with no recent cloud-free Sentinel-2 coverage, or outside ESRI LULC's coverage area, will return a clear error rather than a result

**Forecasting model generalization**: The U-Net forecasting model was trained on land-use transition patterns from 4 zones in Maharashtra, Karnataka, and Andhra Pradesh. Forecasts for regions with similar agro-climatic and urban-growth patterns (e.g. nearby Deccan plateau agricultural belts) are expected to be reasonably reliable. Forecasts for regions with substantially different field geometry, crop patterns, or urbanization styles (e.g. Indo-Gangetic plain, hill agriculture, or non-Indian regions) have not been validated and should be treated as exploratory, not authoritative, until backtested (see below).

---

## Forecast Model — Validated Accuracy (Backtested)

The U-Net forecasting model was backtested by training on data through 2021 and forecasting forward to 2023 — a year for which real ESRI LULC ground truth already exists — across all 4 monitored zones.

| Zone | Pixel Accuracy | ABI Prediction Error |
|------|----------------|----------------------|
| Nashik North | 93.1% | 13.6% |
| Hubli Outskirts | 90.1% | 6.4% |
| Vijayawada West | 88.9% | 2.6% |
| Bengaluru | 91.1% | 10.9% |

These results reflect a 2-year forecast horizon. Accuracy over the full 25-year projection horizon (2025–2051) has not been independently validated, since no ground truth exists for those years. Forecasts beyond ~2-3 years should be treated as directional trend indicators rather than precise predictions.
