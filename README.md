# FarmGuard — Farmland Encroachment & Risk Analytics Platform

Satyukt-aligned Farmland Encroachment Detection System. Rebuilt from UrbanGenesis to track agricultural boundaries, monitor urban sprawl, and calculate the **Agricultural Buffer Index (ABI)** for Sat4Risk flood indexing, crop insurance premium adjustments, and MRV carbon credit baselines.

---

## 🌟 Key Features

- **Cloud-Composite ESRI Land Cover**: Uses the global 10m cloud-free ESRI LULC annual dataset via Planetary Computer STAC.
- **Native 10m/pixel Spatial Resolution**: Processes high-resolution satellite bands and classification masks at native 10m scale.
- **Multi-Stage Date Fallback Search**: Dynamic Sentinel-2 acquisition search window (Strict February → Jan 15 – Mar 15 → Full year fallback) to ensure cloud-free 100% spatial coverage.
- **Agricultural Buffer Index (ABI)**: Computes the ratio of natural buffer to urban infrastructure:
  $$ABI = \frac{\text{Cropland} + \text{Dense Vegetation} + \text{Water Bodies}}{\text{Buildings}}$$
  Handles zero-building zones gracefully by capping ABI at `99.99` to ensure JSON compatibility and correct risk grading.
- **Crop Loss Quantification**: Tracks absolute hectares of cropland converted to built-up area over time.
- **Satyukt Risk Grader**: Converts historical ABI timeseries into risk tiers (Grades A–F) and triggers rapid encroachment alerts.
- **U-Net Forecasting to 2041**: Recursive U-Net inference projects land-cover transitions forward to **2041** with OSM corridor magnetism biasing. Supports both **standard UNet** and **ResNet34UNet** (pretrained backbone) architectures, auto-detected from checkpoint keys.
- **Custom Region Support**: Analyse any user-specified bounding box on-demand. Results cached in `demo/custom_cache/`.
- **Decoupled Full-Stack Design**: Next.js 16 Dashboard + FastAPI Backend with dynamic environment variable support. Map uses ESRI Hybrid Satellite layer (World Imagery + World Boundaries and Places overlay) and a global Nominatim geocoding search bar.

---

## 📂 Project Directory Structure

```
FarmGuard/
├── core/                          # Shared constants and configurations (no internal deps)
│   ├── utils/                     # Unified helper utilities
│   │   ├── bbox_utils.py          # validate_bbox(), bbox_cache_key()
│   │   └── image_utils.py         # rgb_to_mask(), mask_to_rgb()
│   ├── class_map.py               # CLASS_INFO, CLASS_RGB, CLASS_COLORS, ESRI_TO_FARMGUARD
│   └── config.py                  # load_config(), PRECOMPUTED_DIR, safe_float()
├── model/                         # Unified Machine Learning Directory
│   ├── checkpoints/
│   │   └── unet_weights.pt        # Pretrained weights (UNet or ResNet34UNet)
│   ├── architecture.py            # UNet + ResNet34UNet model architectures
│   ├── dataset.py                 # PyTorch dataset and hybrid loss
│   ├── train.py                   # Model training script
│   ├── forecast.py                # Recursive forecasting with load_model_from_checkpoint()
│   └── backtest.py                # Accuracy backtesting suite
├── api/                           # FastAPI HTTP layer
│   ├── main.py                    # create_app() — CORS, middleware, static mount, routers
│   ├── dependencies.py            # load_zone_verdict() (LRU-cached), get_zones_config()
│   └── routes/
│       ├── zones.py               # GET /api/zones
│       ├── analyse.py             # GET /api/analyse, POST /api/analyse_bbox,
│       │                          #   POST /api/forecast_bbox, DELETE, GET /static_custom/
│       └── ...
├── pipeline/                      # ETL / data acquisition layer
│   ├── stac_client.py             # Authenticated STAC client factory
│   ├── landcover_fetcher.py       # fetch_esri_landcover_tile()
│   ├── sentinel_fetcher.py        # fetch_sentinel2_true_color()
│   ├── ndvi.py                    # generate_ndvi_map_from_bands()
│   ├── mock_generator.py          # generate_realistic_mock(), mask_to_true_color()
│   ├── zone_pipeline.py           # generate_zone_assets() — full ETL orchestrator
│   └── custom_region_pipeline.py  # run_custom_region_pipeline() — on-demand ETL
├── analytics/                     # Pure computation — no file I/O
│   ├── __init__.py
│   ├── abi.py                     # ABI calculations and buffer indices
│   ├── change_detection.py        # Transition matrix calculation engine
│   ├── encroachment.py            # calculate_encroachment_stats(), generate_encroachment_heatmap()
│   └── grader.py                  # Satyukt risk grader and alert metrics
├── scripts/                       # Standalone utility scripts
│   └── model_stress_test.py       # Comprehensive 4-suite model audit tool
├── tests/                         # 44 passing tests
│   ├── test_analytics.py          # Python tests for analytical functions and math
│   ├── test_api.py                # API client routing integration tests
│   └── test_encroachment.py       # Pixel-level encroachment verification tests
├── config/
│   └── settings.yaml              # 14 farmland zones, LULC colors, grading thresholds
├── dashboard/                     # Next.js 16 Dashboard client
├── demo/
│   ├── precomputed/               # Precomputed native-res regional files for offline dashboard
│   └── custom_cache/              # On-demand cached results for custom bbox requests
├── docs/                          # Architectural and specification documentation
│   ├── architecture.md            # Architecture topology and data flows
│   ├── platform_specification.md  # Sat4Risk / MRV / LULC classes specification
│   ├── developer_guide.md         # API reference and developer configuration guide
│   ├── modelling.md               # Full mathematical modelling reference
│   └── product.md                 # Product personas, purpose, and design principles
├── app.py                         # Thin shim FastAPI backend server
├── precompute.py                  # CLI entrypoint for the ETL pipeline
├── requirements.txt               # Python backend dependencies
└── README.md                      # This file
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

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
# Optional: Planetary Computer subscription key (anonymous access works too)
PC_SDK_SUBSCRIPTION_KEY=
```

### 3. Run Ingestion Pipeline (ETL)

Generate the precomputed native-resolution assets for registered agricultural zones.

**All zones, live satellite data (requires network):**
```bash
python precompute.py
```

**Single zone:**
```bash
python precompute.py --zone bengaluru
```

**Offline synthetic mock data (no network needed):**
```bash
python precompute.py --mock
```

**Full U-Net recursive forecast to 2041:**
```bash
python precompute.py --forecast
```

All 14 registered zones:

| Zone Key | Description |
|---|---|
| `nashik_north` | Grape and onion belt — Sat4Risk flood zone, MRV baseline |
| `vijayawada_west` | Krishna delta agricultural corridor |
| `hubli_outskirts` | Peri-urban Karnataka farmland fringe |
| `bengaluru` | Satyukt headquarters regional cropland buffer |
| `pune_east` | Rapidly urbanising Deccan fringe |
| `jaipur_south` | Rajasthan semi-arid agricultural zone |
| `ludhiana_rural` | Punjab wheat belt — high-value cropland |
| `coimbatore_north` | Tamil Nadu cotton and sugarcane zone |
| `patna_west` | Indo-Gangetic plain paddy zone |
| `indore_peripheral` | MP soybean belt peri-urban fringe |
| `guwahati_east` | Assam tea and paddy corridor |
| `hyderabad_west` | Telangana cotton and horticulture zone |
| `lucknow_outer` | UP sugar-cane and paddy outer ring |
| `nagpur_rural` | Vidarbha cotton and orange grove belt |

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

Execute the pytest suite (44 passing tests) to verify math logic, bounds capping, and API response shapes:

```bash
PYTHONPATH=. pytest tests/ -v
```

---

## 🔬 Model Stress Testing

Run the comprehensive 4-suite automated model audit:

```bash
PYTHONPATH=. .venv/bin/python scripts/model_stress_test.py --report model_audit_report.md
```

Suites: Historical Backtesting · Physical Transition Integrity · Long-Horizon Stability (→2035) · OSM Road Sensitivity.

---

## 📚 Detailed Documentation

For further details, refer to the documents in the `docs/` folder:
- See [docs/architecture.md](docs/architecture.md) for data flows, sequencing, and component interactions.
- See [docs/modelling.md](docs/modelling.md) for mathematical formulations, U-Net architecture, and inference constraints.
- See [docs/platform_specification.md](docs/platform_specification.md) for Satyukt Sat4Risk/MRV business cases and math index derivations.
- See [docs/developer_guide.md](docs/developer_guide.md) for environment configuration matrices and REST endpoints.
- See [docs/product.md](docs/product.md) for target user personas, core brand personality, and UI design principles.

---

## Custom Region Support — Known Limitations

FarmGuard supports analysis of any user-specified bounding box, subject to:

- **Maximum area**: ~50km × 50km per request (prevents accidental city-or-state-scale requests that would be too slow/expensive to process).
- **Data availability**: Regions with no recent cloud-free Sentinel-2 coverage, or outside ESRI LULC's coverage area, will return a clear error rather than a result.
- **Caching**: On-demand results are cached in `demo/custom_cache/<cache_key>/` and served via the `/static_custom/` endpoint.

**Forecasting model generalization**: The U-Net forecasting model was trained on land-use transition patterns from 4 zones in Maharashtra, Karnataka, and Andhra Pradesh. Forecasts for regions with similar agro-climatic and urban-growth patterns (e.g. nearby Deccan plateau agricultural belts) are expected to be reasonably reliable. Forecasts for regions with substantially different field geometry, crop patterns, or urbanization styles (e.g. Indo-Gangetic plain, hill agriculture, or non-Indian regions) have not been fully validated and should be treated as directional trend indicators, not authoritative predictions, until independently backtested.

---

## Forecast Model — Validated Accuracy (Stress-Test Audit)

The U-Net forecasting model was evaluated via the comprehensive `scripts/model_stress_test.py` audit across multiple prediction intervals. Results for the `2021 → 2023` 2-year horizon (against real ESRI LULC ground truth):

| Zone | Pixel Accuracy | Macro-mIoU | ABI Prediction Error |
|---|---|---|---|
| Bengaluru | 91.30% | 60.74% | 13.0% |
| Hubli Outskirts | 91.42% | 74.83% | 8.9% |
| Nashik North | 92.12% | 67.74% | 5.4% |
| Vijayawada West | 89.55% | 75.64% | 5.1% |

These results reflect a 2-year forecast horizon. The U-Net forecast is run recursively to **2041** (a 18-year horizon from 2023). Accuracy over the full projection horizon has not been independently validated against future ground truth, since no ground truth exists for those years. Forecasts beyond ~2–3 years should be treated as directional trend indicators rather than precise predictions.
