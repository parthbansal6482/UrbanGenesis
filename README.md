# FarmGuard

Satyukt-aligned Farmland Encroachment Detection System. Rebuilt from UrbanGenesis to track agricultural boundaries, monitor urban sprawl, and calculate the Agricultural Buffer Index (ABI) for Sat4Risk flood indexing, crop insurance premium adjustments, and MRV carbon credit baselines.

## Features
- **Cloud-Composite ESRI Land Cover**: Transitioned from the local SegFormer-based model to the global 10m cloud-free ESRI LULC annual dataset via Planetary Computer STAC.
- **Native 10m/pixel Resolution**: All satellite imagery, NDVI maps, and classification masks are processed at native 10m spatial resolution.
- **Multi-Stage Date Fallback Search**: Dynamic Sentinel-2 acquisition window search (Strict February -> Jan 15 - Mar 15 -> Full year fallback) to ensure cloud-free 100% spatial coverage and eliminate black orbital swath/MGRS row gaps.
- **Agricultural Buffer Index (ABI)**: Computes the ratio of natural buffer to urban infrastructure:
  $$ABI = \frac{\text{Cropland} + \text{Dense Vegetation} + \text{Water}}{\text{Buildings} + \text{Roads}}$$
- **Crop Loss Quantification**: Tracks absolute hectares of cropland converted to built-up area over time using 10m spatial resolution.
- **Satyukt Risk Grader**: Converts historical ABI timeseries into risk tiers (Grades A-F) and flags rapid encroachment alerts.

## Project Structure
```
FarmGuard/
├── config/
│   └── settings.yaml          # Farmland zones, class color maps, and ABI grading thresholds
├── analytics/
│   ├── __init__.py
│   ├── abi.py                 # ABI and cropland loss calculation
│   ├── change_detection.py    # Transition matrix engine
│   └── grader.py              # Satyukt risk grader and encroachment flags
├── demo/
│   └── precomputed/           # Precomputed native-res assets for Satyukt zones (tracked)
├── scripts/
│   └── fetch_esri_landcover.py # Main pipeline: fetch ESRI LULC + Sentinel-2 imagery
├── tests/
│   └── test_analytics.py      # Test suite for ABI, grader, and crop loss
├── requirements.txt
├── .env.example
└── README.md
```

## Running the System

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Fetch ESRI LULC and Sentinel-2 Imagery**:
   Generate the precomputed native-resolution assets for all agricultural zones:
   ```bash
   python scripts/fetch_esri_landcover.py --zone all
   ```
   *Available zones in config: `nashik_north`, `vijayawada_west`, `hubli_outskirts`, `bengaluru`*

3. **Launch the FastAPI Backend**:
   ```bash
   PYTHONPATH=. python app.py
   ```

4. **Launch the Next.js Dashboard**:
   ```bash
   cd dashboard && npm run dev
   ```
   Open `http://localhost:3000` to view the encroachment dashboard.

## Testing
Verify the analytics, ABI grading, and cropland loss codebase using `pytest`:
```bash
PYTHONPATH=. pytest tests/ -v
```

## Tech Stack
FastAPI · Next.js · Leaflet · PyTorch · pystac-client · planetary-computer · numpy · Pillow
