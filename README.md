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
├── config/
│   └── settings.yaml          # Farmland zones, LULC colors, and grading thresholds
├── docs/                      # Architectural and specification documentation
│   ├── architecture.md        # Architecture topology and data flows
│   ├── platform_specification.md # Sat4Risk / MRV / LULC classes specification
│   └── developer_guide.md     # API reference and developer configuration guide
├── analytics/                 # Core analytical code
│   ├── __init__.py
│   ├── abi.py                 # ABI calculations, missing metrics, and infinity capping
│   ├── change_detection.py    # Transition matrix calculation engine
│   └── grader.py              # Satyukt risk grader and alert metrics
├── dashboard/                 # Next.js 16 Dashboard client
├── demo/
│   └── precomputed/           # Precomputed native-res regional files for offline dashboard
├── scripts/
│   └── fetch_esri_landcover.py # Planetary Computer ETL pipeline
├── tests/
│   ├── test_analytics.py      # Python tests for analytical functions and math
│   ├── test_api.py            # API client routing integration tests
│   └── test_encroachment.py   # Pixel-level encroachment verification tests
├── app.py                     # FastAPI backend server
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
Generate the precomputed native-resolution assets for registered agricultural zones:
```bash
python scripts/fetch_esri_landcover.py --zone all
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
