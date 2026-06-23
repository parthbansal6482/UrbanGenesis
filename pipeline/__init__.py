"""
pipeline — ETL and data acquisition layer for FarmGuard.

Modules:
    stac_client        — Authenticated STAC API client factory
    landcover_fetcher  — ESRI Annual Land Cover tile retrieval
    sentinel_fetcher   — Sentinel-2 true-color imagery retrieval
    ndvi               — NDVI map generation from spectral bands
    mock_generator     — Spatially-coherent synthetic data for offline use
    zone_pipeline      — Top-level orchestrator: generate_zone_assets()

Entry point:
    Use ``run_pipeline.py`` at the project root for CLI usage:
        python run_pipeline.py --zone nashik_north --mock
"""
