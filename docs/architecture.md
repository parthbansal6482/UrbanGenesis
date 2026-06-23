# Architecture Design — FarmGuard

This document details the system architecture, directory topology, and data flow of the FarmGuard/UrbanGenesis Farmland Encroachment Detection System.

---

## System Overview

FarmGuard is a decoupled, modular full-stack platform consisting of four distinct layers:

1. **Planetary Computer ETL Pipeline** (`pipeline/`): An ingestion engine that queries Sentinel-2 Level-2A imagery and ESRI Land Use / Land Cover (LULC) maps from Microsoft Planetary Computer via the STAC API.
2. **FastAPI Backend Services** (`api/`): A Python-based REST API that runs spatial analytics, serves region configuration, manages timeseries records, and caches dynamic heatmaps.
3. **Shared Core** (`core/`): A dependency-free kernel of class definitions, configuration loaders, and image utilities shared between the API and pipeline layers.
4. **Next.js 16 Dashboard** (`dashboard/`): An interactive, premium web client with React Leaflet map projections, comparative split-sliders, and data visualization timelines.

---

## Directory Topology

```
UrbanGenesis/
│
├── core/                        # Shared constants and utilities (no internal deps)
│   ├── class_map.py             # CLASS_INFO, CLASS_RGB, CLASS_COLORS, ESRI_TO_FARMGUARD
│   ├── config.py                # load_config(), PRECOMPUTED_DIR, safe_float()
│   └── image_utils.py           # rgb_to_mask(), mask_to_rgb()
│
├── api/                         # FastAPI HTTP layer
│   ├── main.py                  # create_app() — CORS, middleware, static mount, routers
│   ├── dependencies.py          # load_zone_verdict() (LRU-cached), get_zones_config()
│   └── routes/
│       ├── zones.py             # GET /api/zones
│       └── analyse.py           # GET /api/analyse
│
├── pipeline/                    # ETL / data acquisition layer
│   ├── stac_client.py           # create_stac_client() — authenticated STAC client factory
│   ├── landcover_fetcher.py     # fetch_esri_landcover_tile()
│   ├── sentinel_fetcher.py      # fetch_sentinel2_true_color()
│   ├── ndvi.py                  # generate_ndvi_map_from_bands()
│   ├── mock_generator.py        # generate_realistic_mock(), mask_to_true_color()
│   └── zone_pipeline.py         # generate_zone_assets() — full orchestrator
│
├── analytics/                   # Pure computation — no file I/O
│   ├── abi.py                   # compute_abi(), compute_abi_timeseries()
│   ├── change_detection.py      # compute_transition_matrix(), detect_urban_expansion()
│   ├── encroachment.py          # calculate_encroachment_stats(), generate_encroachment_heatmap()
│   └── grader.py                # assign_grade(), detect_encroachment_alert(), generate_verdict()
│
├── tests/
│   ├── test_analytics.py        # Unit tests for analytics modules
│   ├── test_api.py              # API integration tests
│   └── test_encroachment.py     # Encroachment calculation tests
│
├── config/
│   └── settings.yaml            # Zone definitions, model config, STAC endpoint
│
├── dashboard/                   # Next.js 16 frontend
├── demo/precomputed/            # Precomputed PNGs and verdict.json files
├── docs/                        # Architecture, platform spec, developer guide
│
├── app.py                       # Thin shim: `from api.main import create_app`
└── run_pipeline.py              # CLI entrypoint for the ETL pipeline
```

---

## Dependency Flow

Each layer only imports from layers below it. No circular imports.

```
  api/routes/   →  api/dependencies  →  core/,  analytics/
  pipeline/     →  core/,  analytics/
  analytics/    →  (numpy, scipy — no FarmGuard internals)
  core/         →  (no internal project dependencies)

  app.py        →  api/main.py  (thin shim only)
  run_pipeline  →  pipeline/zone_pipeline.py
```

---

## Component Details

### 1. Shared Core (`core/`)

The dependency-free kernel. Every other package may freely import from here.

- **`class_map.py`**: Single source of truth for all land-cover class IDs, hex colors, and ESRI→FarmGuard remapping. Eliminates duplication that previously existed between `app.py` and the old monolithic script.
- **`config.py`**: Loads `config/settings.yaml` once at import time and exposes `ZONES_CONFIG`, `PRECOMPUTED_DIR`, and `safe_float()` — the NaN/Infinity sanitizer used before any JSON serialization.
- **`image_utils.py`**: Vectorized `rgb_to_mask()` and `mask_to_rgb()` — used by both the API (dynamic heatmap generation) and the pipeline (precomputed asset generation).

### 2. Ingestion Pipeline (`pipeline/`)

- **`stac_client.py`**: Authenticated STAC client factory using `planetary_computer.sign_inplace`. Shared by both land cover and Sentinel-2 fetchers.
- **`landcover_fetcher.py`**: Retrieves ESRI Annual Land Cover tiles (2017–2023), mosaics multi-tile results, and remaps ESRI class IDs to the FarmGuard schema using `core.class_map.ESRI_TO_FARMGUARD`.
- **`sentinel_fetcher.py`**: Multi-stage date search strategy (February → Q1 → full-year) to find the lowest-cloud, highest-coverage Sentinel-2 composite. Bands downloaded in parallel via `ThreadPoolExecutor`.
- **`ndvi.py`**: Computes `(NIR - Red) / (NIR + Red)` and applies the `RdYlGn` colormap.
- **`mock_generator.py`**: Gaussian-blur rank-assignment mock for offline development. Zone-specific class proportion profiles with time-interpolated drift rates.
- **`zone_pipeline.py`**: Orchestrates all of the above for a single zone/year. Writes `true_color_YYYY.png`, `ndvi_map_YYYY.png`, `mask_rgb_YYYY.png`, `encroachment_heatmap.png`, and `verdict.json` to `demo/precomputed/<zone_key>/`.

### 3. Analytical Engine (`analytics/`)

Pure computation — no file I/O, no HTTP, no FarmGuard-internal imports.

- **`abi.py`**: Computes the Agricultural Buffer Index:
  $$ABI = \frac{\text{Cropland} + \text{Dense Vegetation} + \text{Water Bodies}}{\text{Buildings}}$$
  Capped at `99.99` when buildings = 0 to prevent JSON serialization errors.
- **`change_detection.py`**: Builds transition matrices mapping land changes between any two years.
- **`encroachment.py`**: Calculates cropland/water loss to buildings in hectares; generates encroachment heatmap RGB arrays.
- **`grader.py`**: Converts ABI into A–F risk grades; detects rapid ABI drops (≥20% in ≤5 years) as encroachment alerts.

### 4. FastAPI Backend (`api/`)

- **`main.py`**: `create_app()` factory — CORS (env-driven), Cache-Control middleware for `/static/*`, static file mount, router registration.
- **`dependencies.py`**: `load_zone_verdict()` with `@functools.lru_cache(maxsize=16)` — in-process caching of verdict.json files. Sanitizes raw JSON for NaN/Infinity before returning.
- **`routes/zones.py`**: `GET /api/zones` — returns all zones with summary metrics. `Cache-Control: public, max-age=300`.
- **`routes/analyse.py`**: `GET /api/analyse` — full zone analysis with dynamic encroachment heatmap generation and caching, year-range comparison, transitions, and overlay URLs.

### 5. Next.js 16 Dashboard (`dashboard/`)

- **Interactive Map**: Leaflet overlays projecting RGB masks, True Color bands, and NDVI. Comparative split-screen sliding.
- **Timeline Visualization**: Custom SVG `LineChart` and `EncroachmentChart` for historical ABI and component trends.
- **Fault-Tolerance**: Seamless offline fallback to pre-packaged timeseries data when the backend is unreachable.

---

## Run Commands

```bash
# Start the API server (development)
UVICORN_RELOAD=true PYTHONPATH=. python app.py

# Run all tests
PYTHONPATH=. pytest tests/ -v

# Run ETL pipeline (live satellite data)
python run_pipeline.py --zone nashik_north

# Run ETL pipeline (offline synthetic data)
python run_pipeline.py --mock

# Start the Next.js dashboard
cd dashboard && npm run dev
```
