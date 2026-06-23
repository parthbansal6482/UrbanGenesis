#!/usr/bin/env python
"""
run_pipeline.py — FarmGuard ETL pipeline CLI.

Fetches ESRI Annual Land Cover + Sentinel-2 imagery from Microsoft
Planetary Computer and generates precomputed demo assets under
``demo/precomputed/<zone_key>/``.

Usage:
    # Process all zones using live satellite data
    python run_pipeline.py

    # Process a single zone using live data
    python run_pipeline.py --zone nashik_north

    # Process all zones using fast synthetic mock data (no network)
    python run_pipeline.py --mock

    # Process one zone with mock data
    python run_pipeline.py --zone bengaluru --mock

Options:
    --zone ZONE_KEY   Process only the specified zone (default: all)
    --mock            Use spatially-coherent synthetic data instead of
                      querying Planetary Computer (faster, offline-safe)
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

# Ensure the project root is on sys.path when the script is run directly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.zone_pipeline import generate_zone_assets

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("run_pipeline")

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "settings.yaml"


def _load_zones() -> dict:
    """Load zone definitions from settings.yaml."""
    try:
        with open(CONFIG_PATH) as fh:
            cfg = yaml.safe_load(fh)
        return cfg.get("zones", {})
    except Exception as exc:
        logger.error("Failed to load config/settings.yaml: %s", exc)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FarmGuard ETL pipeline — generate precomputed demo assets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--zone",
        default="all",
        metavar="ZONE_KEY",
        help="Zone key to process, or 'all' (default: all)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use synthetic mock data (no Planetary Computer network calls)",
    )
    args = parser.parse_args()

    all_zones = _load_zones()

    if args.zone != "all":
        zones = {k: v for k, v in all_zones.items() if k == args.zone}
        if not zones:
            logger.error("Zone '%s' not found in settings.yaml.", args.zone)
            logger.error("Available zones: %s", ", ".join(all_zones.keys()))
            sys.exit(1)
    else:
        zones = all_zones

    use_network = not args.mock
    mode_label = (
        "Network mode (ESRI Land Cover + Sentinel-2 from Planetary Computer)"
        if use_network
        else "Mock mode (spatially-coherent synthetic data — no network)"
    )
    logger.info("Mode: %s", mode_label)
    logger.info("Zones to process: %s", ", ".join(zones.keys()))

    for zone_key, zone_cfg in zones.items():
        bbox = zone_cfg.get("bbox")
        years = zone_cfg.get("years", [2017, 2019, 2021, 2023])
        logger.info("\n%s", "=" * 60)
        logger.info(
            "Zone: %s  |  BBox: %s  |  Years: %s",
            zone_cfg.get("name", zone_key), bbox, years,
        )
        generate_zone_assets(zone_key, bbox, years, use_network=use_network)

    logger.info("\nAll zones processed.")
    from core.config import PRECOMPUTED_DIR
    logger.info("Assets saved to: %s", PRECOMPUTED_DIR)


if __name__ == "__main__":
    main()
