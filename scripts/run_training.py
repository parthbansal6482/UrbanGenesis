"""
scripts/run_training.py

CLI script to fine-tune the FarmGuard SegFormer model (7 classes including cropland).
Run from Colab with GPU — not intended for local CPU execution.
Usage: python3 scripts/run_training.py --config config/settings.yaml
"""

import argparse
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from model.train import train

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Run FarmGuard SegFormer Training (7-class model).")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to settings.yaml")
    args = parser.parse_args()

    logger.info(f"Starting model training with configuration: {args.config}")
    best_miou = train(args.config)
    logger.info(f"Training completed. Best validation mIoU: {best_miou:.4f}")

if __name__ == "__main__":
    main()
