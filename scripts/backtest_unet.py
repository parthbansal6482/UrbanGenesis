"""
scripts/backtest_unet.py

Backtests the U-Net forecasting model against known historical outcomes.
Instead of forecasting an unverifiable future year, this script:
  1. Trains (or loads a model trained) using only data up to a cutoff year
  2. Forecasts forward to a year we already have real ESRI LULC data for
  3. Compares the forecast against the real outcome
  4. Reports accuracy metrics

This is the single most important credibility check for the forecasting
feature — it proves whether the model's predictions should be trusted.
"""

import argparse
import logging
from pathlib import Path
import numpy as np
from PIL import Image
import sys

# Setup project root path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.unet_model import UNet
from core.unet_dataset import GlobalPatchDataset
from analytics.abi import compute_abi

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def compute_pixel_accuracy(pred_mask: np.ndarray, true_mask: np.ndarray) -> float:
    """Fraction of pixels where prediction matches ground truth exactly."""
    assert pred_mask.shape == true_mask.shape, "Shape mismatch between prediction and ground truth"
    return float((pred_mask == true_mask).mean())


def compute_per_class_iou(pred_mask: np.ndarray, true_mask: np.ndarray, num_classes: int = 6) -> dict:
    """IoU per class — tells you which land-cover types the model predicts well vs poorly."""
    iou_per_class = {}
    for cls in range(num_classes):
        pred_cls = (pred_mask == cls)
        true_cls = (true_mask == cls)
        intersection = (pred_cls & true_cls).sum()
        union = (pred_cls | true_cls).sum()
        iou_per_class[cls] = float(intersection / union) if union > 0 else None
    return iou_per_class


def compute_abi_prediction_error(pred_mask: np.ndarray, true_mask: np.ndarray) -> dict:
    """
    The most business-relevant metric: how far off was the predicted
    ABI score from the real ABI score? This matters more than raw pixel
    accuracy, since ABI is the number actually used for risk grading.
    """
    pred_abi = compute_abi(pred_mask)["abi"]
    true_abi = compute_abi(true_mask)["abi"]
    abs_error = abs(pred_abi - true_abi)
    pct_error = (abs_error / true_abi * 100) if true_abi > 0 else 0.0
    return {
        "predicted_abi": pred_abi,
        "actual_abi": true_abi,
        "absolute_error": abs_error,
        "percent_error": pct_error,
    }


def run_backtest(
    zone_key: str,
    cutoff_year: int,
    target_year: int,
    model_checkpoint: Path,
    precomputed_dir: Path = Path("demo/precomputed"),
) -> dict:
    """
    Runs a single backtest for one zone:
    forecasts target_year using only data available up to cutoff_year,
    then compares against the real target_year ground truth.
    """
    zone_dir = precomputed_dir / zone_key

    # Load the real ground truth for the target year (already exists from ETL)
    true_mask_path = zone_dir / f"mask_rgb_{target_year}.png"
    if not true_mask_path.exists():
        raise FileNotFoundError(
            f"No ground truth available for {zone_key} in {target_year}. "
            f"Backtesting requires a year with real historical data, not a future projection."
        )

    from core.image_utils import rgb_to_mask
    true_mask = rgb_to_mask(np.array(Image.open(true_mask_path)))

    # Run the model forward from cutoff_year to target_year
    from scripts.forecast_unet import forecast_zone
    pred_mask = forecast_zone(
        zone_key=zone_key,
        start_year=cutoff_year,
        target_year=target_year,
        checkpoint_path=model_checkpoint,
        zone_dir=zone_dir,
    )

    if pred_mask is None:
        raise ValueError("Forecasting returned None mask")

    results = {
        "zone": zone_key,
        "cutoff_year": cutoff_year,
        "target_year": target_year,
        "pixel_accuracy": compute_pixel_accuracy(pred_mask, true_mask),
        "per_class_iou": compute_per_class_iou(pred_mask, true_mask),
        "abi_error": compute_abi_prediction_error(pred_mask, true_mask),
    }

    logger.info(f"Backtest results for {zone_key} ({cutoff_year} → {target_year}):")
    logger.info(f"  Pixel accuracy: {results['pixel_accuracy']:.3f}")
    logger.info(f"  ABI prediction error: {results['abi_error']['percent_error']:.1f}%")

    return results


def save_visual_comparison(pred_mask, true_mask, output_path: Path):
    """Saves a side-by-side PNG: predicted mask | actual mask | difference map."""
    from core.image_utils import mask_to_rgb

    pred_rgb = mask_to_rgb(pred_mask)
    true_rgb = mask_to_rgb(true_mask)
    diff = (pred_mask != true_mask).astype(np.uint8) * 255
    diff_rgb = np.stack([diff, np.zeros_like(diff), np.zeros_like(diff)], axis=-1)

    combined = np.concatenate([true_rgb, pred_rgb, diff_rgb], axis=1)
    Image.fromarray(combined).save(output_path)
    logger.info(f"Saved visual comparison to {output_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone", required=True, choices=[
        "bengaluru", "hubli_outskirts", "nashik_north", "vijayawada_west"
    ])
    parser.add_argument("--cutoff-year", type=int, default=2021,
                         help="Last year of real data the model is allowed to use")
    parser.add_argument("--target-year", type=int, default=2023,
                         help="Year to forecast and compare against real ground truth")
    parser.add_argument("--checkpoint", type=Path, default=Path("model/checkpoints/unet_weights.pt"))
    parser.add_argument("--output-dir", type=Path, default=Path("backtest_results"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = run_backtest(args.zone, args.cutoff_year, args.target_year, args.checkpoint)

    import json
    results_path = args.output_dir / f"backtest_{args.zone}_{args.cutoff_year}_{args.target_year}.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Saved results to {results_path}")


if __name__ == "__main__":
    main()
