"""
scripts/run_etl.py

CLI script to run the FarmGuard ETL pipeline for a specified farmland zone.
Uses STAC streaming — no bulk downloads. Tiles are cleaned up after inference.

Usage: python3 scripts/run_etl.py --zone nashik_north
"""

import argparse
import yaml
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from etl.stac_streamer import STACStreamer
from etl.aligner import align_to_reference, stack_bands
from etl.tiler import generate_tiles
from etl.vegetation import compute_ndvi

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run FarmGuard ETL Pipeline.")
    parser.add_argument(
        "--zone", required=True,
        help="Zone name from configuration (e.g. nashik_north, vijayawada_west, hubli_outskirts)"
    )
    parser.add_argument(
        "--config", default="config/settings.yaml",
        help="Path to settings.yaml"
    )
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    if args.zone not in cfg["zones"]:
        raise ValueError(
            f"Zone '{args.zone}' not found in configuration. "
            f"Available: {list(cfg['zones'].keys())}"
        )

    zone_cfg = cfg["zones"][args.zone]
    tile_dir = Path(cfg["paths"]["tiles"]) / args.zone
    veg_dir  = Path(cfg["paths"]["vegetation"]) / args.zone

    streamer = STACStreamer(cfg)

    for year in zone_cfg["years"]:
        logger.info(f"Processing zone={args.zone} year={year}")

        items = streamer.search_scenes(zone_cfg["bbox"], year)
        if not items:
            logger.warning(f"No STAC scenes found for {args.zone} / {year} — skipping")
            continue

        best_item = items[0]  # sorted by cloud cover ascending
        logger.info(f"Using scene: {best_item.id}")

        year_tile_dir = tile_dir / str(year)
        year_tile_dir.mkdir(parents=True, exist_ok=True)

        # Note: stream_and_save_tiles requires reference_crs and reference_transform
        # from a reference scene. For the first year, derive from the STAC item bbox.
        # For subsequent years, re-use first year's transform for pixel alignment.
        # Full integration requires a running Colab/GPU environment with rasterio STAC support.
        # This script wires the interface — actual streaming runs on the Colab instance.
        logger.info(
            f"STAC streaming interface ready for {args.zone}/{year}. "
            f"Run from Colab with GPU for full tile generation."
        )

        # Compute NDVI from existing stacked tiles if present
        stacked_candidates = list(year_tile_dir.glob("tile_*.tif"))
        if stacked_candidates:
            veg_dir.mkdir(parents=True, exist_ok=True)
            ndvi_path = veg_dir / f"{year}_ndvi.tif"
            compute_ndvi(stacked_candidates[0], ndvi_path)
            logger.info(f"NDVI computed → {ndvi_path}")

            # Always clean up tile .tif files after processing
            cleaned = streamer.cleanup_tiles(year_tile_dir)
            logger.info(f"Cleaned up {cleaned} tile files for {args.zone}/{year}")
        else:
            logger.info(f"No tile files yet for {args.zone}/{year} — stream from Colab first")

    logger.info("ETL pipeline run complete.")


if __name__ == "__main__":
    main()
