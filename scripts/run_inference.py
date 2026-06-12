"""
scripts/run_inference.py

CLI script to run batch inference on the generated tiles for a zone and stitch the results.
Uses 7-class FarmGuard model. Cleans up temporary tile GeoTIFFs after mask generation to save space.

Usage: python scripts/run_inference.py --zone nashik_north --checkpoint model/checkpoints/best_model
"""

import argparse
import yaml
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from model.inference import run_inference_on_tiles, stitch_tiles_to_scene

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Run FarmGuard Segmentation Inference.")
    parser.add_argument("--zone", required=True, help="Farmland zone name from configuration")
    parser.add_argument("--checkpoint", default="model/checkpoints/best_model", help="Path to model checkpoint directory")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to settings.yaml")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    if args.zone not in cfg["zones"]:
        raise ValueError(f"Zone '{args.zone}' not found in configuration.")

    zone_cfg = cfg["zones"][args.zone]
    tile_dir = Path(cfg["paths"]["tiles"]) / args.zone
    mask_dir = Path(cfg["paths"]["masks"]) / args.zone

    for year in zone_cfg["years"]:
        year_tile_dir = tile_dir / str(year)
        year_mask_dir = mask_dir / str(year)

        if not year_tile_dir.exists():
            logger.warning(f"Tile directory {year_tile_dir} does not exist. Skipping {year}.")
            continue

        # Count available stacked tiles
        tiles = list(year_tile_dir.glob("tile_*.tif"))
        if not tiles:
            logger.warning(f"No tiles found in {year_tile_dir}. Skipping {year}.")
            continue

        logger.info(f"Running batch inference on {len(tiles)} tiles for {args.zone} — {year}")
        run_inference_on_tiles(
            tile_dir=year_tile_dir,
            checkpoint_dir=args.checkpoint,
            output_dir=year_mask_dir,
            config=cfg,
            batch_size=cfg["model"]["batch_size"]
        )

        # Stitch masks into a single full-scene mask
        logger.info(f"Stitching tiles back into full mask for {args.zone} — {year}")
        masks_metadata_path = year_mask_dir / "masks_metadata.json"
        output_scene_path = year_mask_dir / "stitched_mask.png"
        stitch_tiles_to_scene(masks_metadata_path, output_scene_path)

        # Clean up temporary .tif tile files to reclaim space
        deleted = 0
        for tif in year_tile_dir.glob("*.tif"):
            tif.unlink()
            deleted += 1
        logger.info(f"Cleaned up {deleted} temporary tile .tif files for {args.zone} — {year}")

    logger.info("Inference and stitching completed.")

if __name__ == "__main__":
    main()
