# FarmGuard

Satyukt-aligned Farmland Encroachment Detection System. Rebuilt from UrbanGenesis to track agricultural boundaries, monitor urban sprawl, and calculate the Agricultural Buffer Index (ABI) for Sat4Risk flood indexing, crop insurance premium adjustments, and MRV carbon credit baselines.

## Features
- **STAC Streaming**: Streams Sentinel-2 L2A tiles directly from Microsoft Planetary Computer on demand (no massive scene downloads, automatic temporary file cleanup).
- **7-Class Segmentation**: SegFormer-based model classifies pixels into 7 distinct land categories (Background, Buildings, Roads, Cropland, Dense Vegetation, Water, Bare Soil).
- **Agricultural Buffer Index (ABI)**: Computes the ratio of natural buffer to urban infrastructure:
  $$ABI = \frac{\text{Cropland} + \text{Dense Vegetation} + \text{Water}}{\text{Buildings} + \text{Roads}}$$
- **Crop Loss Quantification**: Tracks absolute hectares of cropland converted to built-up area over time using Sentinel-2 10m spatial resolution.
- **Satyukt Risk Grader**: Converts historical ABI timeseries into risk tiers (Grades A-F) and flags rapid encroachment alerts.

## Project Structure
```
FarmGuard/
├── config/
│   └── settings.yaml          # 7-class color maps, farmland zones, and ABI grading thresholds
├── data/
│   ├── raw/                   # Temporary raw data directory (gitignored)
│   ├── tiles/                 # 512x512 tile chunks (gitignored)
│   ├── masks/                 # Model prediction masks (gitignored)
│   └── vegetation/            # Saved NDVI/vegetation products (gitignored)
├── etl/
│   ├── __init__.py
│   ├── stac_streamer.py       # COG windowed streaming from Planetary Computer
│   ├── aligner.py             # Spatial CRS alignment across years
│   ├── tiler.py               # Sliding window chunker
│   └── vegetation.py          # NDVI and cropland fraction metrics
├── model/
│   ├── __init__.py
│   ├── dataset.py             # 7-class PyTorch Dataset
│   ├── train.py               # Fine-tuning loop (label smoothing, auxiliary loss)
│   ├── inference.py           # Batch tile inference and stitching
│   └── checkpoints/           # Trained weights (gitignored)
├── analytics/
│   ├── __init__.py
│   ├── abi.py                 # ABI and cropland loss calculation
│   ├── change_detection.py    # Transition matrix engine
│   └── grader.py              # Satyukt risk grader and encroachment flags
├── demo/
│   ├── app.py                 # Gradio web application
│   └── precomputed/           # Pre-run results for Satyukt zones (tracked)
├── scripts/
│   ├── run_etl.py             # CLI: run STAC streaming and vegetation index pipeline
│   ├── run_training.py        # CLI: launch model fine-tuning
│   ├── run_inference.py       # CLI: run batch inference on zone tiles
│   └── precompute_demo.py     # CLI: generate precomputed assets for app
├── tests/
│   ├── test_etl.py            # Test suite for streaming and vegetation metrics
│   ├── test_analytics.py      # Test suite for ABI, grader, and crop loss
│   └── test_model.py          # Test suite for SegFormer inputs and outputs
├── requirements.txt
├── .env.example
└── README.md
```

## Running the System

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run ETL for an Agricultural Zone** (STAC Tile Streaming):
   ```bash
   python scripts/run_etl.py --zone nashik_north
   ```
   *Available zones in config: `nashik_north`, `vijayawada_west`, `hubli_outskirts`*

3. **Fine-tune the SegFormer Model**:
   ```bash
   python scripts/run_training.py
   ```

4. **Run Inference & Clean Up Tiles**:
   ```bash
   python scripts/run_inference.py --zone nashik_north --checkpoint model/checkpoints/best_model
   ```

5. **Precompute Results for the Demo**:
   ```bash
   python scripts/precompute_demo.py --zone nashik_north
   ```

6. **Launch the Gradio Web App**:
   ```bash
   python demo/app.py
   ```

## Testing
Verify the entire streaming, segmentation, and analytics codebase using `pytest`:
```bash
PYTHONPATH=. pytest tests/ -v
```

## Tech Stack
rasterio · PyTorch · HuggingFace Transformers · Gradio · Plotly · pystac-client · planetary-computer
