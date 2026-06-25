"""
scripts/forecast_unet.py

Uses a pre-trained U-Net model checkpoint to evaluate validation accuracy on 2023,
forecast future years recursively up to 2051, and generate dashboard assets.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import torch
import yaml
from PIL import Image
from torch.utils.data import DataLoader

# Setup project root path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.abi import compute_abi, compute_cropland_loss_ha
from analytics.grader import generate_verdict
from core.class_map import CLASS_COLORS
from core.config import CONFIG_PATH, PRECOMPUTED_DIR
from core.image_utils import mask_to_rgb, rgb_to_mask
from core.unet_dataset import GlobalPatchDataset
from core.unet_model import UNet

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("forecast_unet")

# Allowed transition matrix: [from_class, to_class]
ALLOWED_TRANSITIONS = np.array([
    [True, True, True, True, True, True],  # 0 (bg): can stay bg or transition to anything
    [False, True, False, False, False, False],  # 1 (bld): can ONLY stay building (strict persistence)
    [False, True, True, False, False, True],  # 2 (crop): can become bld or soil, but NOT veg or water
    [False, True, True, True, False, True],  # 3 (veg): can become bld, crop, soil, or stay veg, but NOT water
    [False, True, True, False, True, True],  # 4 (wat): can become bld, crop, soil, or stay water, but NOT veg
    [False, True, True, False, False, True],  # 5 (soil): can become bld, crop, or stay soil, but NOT veg or water
], dtype=bool)


def forecast_zone(
    zone_key: str,
    model: UNet = None,
    device: torch.device = None,
    batch_size: int = 8,
    num_workers: int = 0,
    pin_memory: bool = False,
    use_amp: bool = False,
    start_year: int = 2023,
    target_year: int = 2051,
    checkpoint_path: Path = None,
    zone_dir: Path = None,
) -> np.ndarray | None:
    """Run recursive spatial land-cover forecasting for a single zone."""
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if model is None:
        model = UNet(in_channels=22, out_channels=6).to(device)
        if checkpoint_path and Path(checkpoint_path).exists():
            model.load_state_dict(torch.load(checkpoint_path, map_location=device))
        model.eval()

    forecast_years = list(range(start_year + 2, target_year + 1, 2))
    if zone_dir is None:
        zone_dir = PRECOMPUTED_DIR / zone_key

    # Load historical masks up to start_year
    masks = {}
    historical_years = [y for y in [2017, 2019, 2021, 2023] if y <= start_year]
    for yr in historical_years:
        img = np.array(Image.open(zone_dir / f"mask_rgb_{yr}.png").convert("RGB"))
        masks[yr] = rgb_to_mask(img)

    h, w = masks[historical_years[0]].shape

    for target_yr in forecast_years:
        y_prev = target_yr - 2
        y_prev2 = target_yr - 4

        # Forecast dataset for single target year
        forecast_dataset = GlobalPatchDataset([zone_key], y_prev2, y_prev, None, patch_size=128, augment=False)
        forecast_loader = DataLoader(
            forecast_dataset,
            batch_size=batch_size,
            shuffle=False,
            num_workers=num_workers,
            pin_memory=pin_memory,
        )

        h_crop = forecast_dataset.h_patches * 128
        w_crop = forecast_dataset.w_patches * 128
        forecast_mask = np.zeros((h_crop, w_crop), dtype=np.uint8)

        patch_idx = 0
        with torch.no_grad():
            for X_batch, prev_batch in forecast_loader:
                X_batch, prev_batch = X_batch.to(device), prev_batch.to(device)
                with torch.amp.autocast("cuda", enabled=use_amp):
                    outputs = model(X_batch)
                    # Apply transition constraints by masking logits
                    allowed_tensor = torch.tensor(ALLOWED_TRANSITIONS, device=device, dtype=torch.bool)
                    mask = allowed_tensor[prev_batch].permute(0, 3, 1, 2)
                    outputs_masked = outputs.clone()
                    outputs_masked[~mask] = -1e9
                    preds = torch.argmax(outputs_masked, dim=1).cpu().numpy()

                for b in range(preds.shape[0]):
                    py = patch_idx // forecast_dataset.w_patches
                    px = patch_idx % forecast_dataset.w_patches
                    y = py * 128
                    x = px * 128
                    forecast_mask[y : y + 128, x : x + 128] = preds[b]
                    patch_idx += 1

        # Crop back to original dimensions
        full_forecast_mask = forecast_mask[:h, :w]

        # Apply building persistence constraint
        prev_mask = masks[y_prev]
        full_forecast_mask[prev_mask == 1] = 1

        masks[target_yr] = full_forecast_mask

        # For historical backtesting, we do NOT want to overwrite the zone's standard forward-looking forecast files!
        if target_yr > 2023:
            # Save predicted mask
            forecast_rgb = mask_to_rgb(full_forecast_mask)
            output_path = zone_dir / f"mask_rgb_{target_yr}.png"
            Image.fromarray(forecast_rgb).save(output_path)
            logger.info(f"  Saved U-Net forecasted mask for {target_yr}: {output_path.name}")

    if target_year <= 2023:
        return masks[target_year]

    # Rebuild complete timeseries with forecasts
    new_timeseries = []
    for yr in [2017, 2019, 2021, 2023] + forecast_years:
        yr_mask = masks[yr]
        yr_stats = compute_abi(yr_mask)
        yr_stats["year"] = yr
        yr_stats["soil_pixels"] = int((yr_mask == 5).sum())
        yr_stats["soil_pct"] = round(yr_stats["soil_pixels"] / yr_mask.size * 100, 2)
        yr_stats["buildings_pct"] = round(yr_stats["buildings_pixels"] / yr_mask.size * 100, 2)
        yr_stats["vegetation_pct"] = round(yr_stats["vegetation_pixels"] / yr_mask.size * 100, 2)
        yr_stats["water_pct"] = round(yr_stats["water_pixels"] / yr_mask.size * 100, 2)
        yr_stats["cropland_pct"] = round(yr_stats["cropland_pixels"] / yr_mask.size * 100, 2)
        new_timeseries.append(yr_stats)

    new_timeseries = sorted(new_timeseries, key=lambda x: x["year"])

    # Calculate overall cropland loss 2017 -> 2051
    loss_ha = compute_cropland_loss_ha(masks[2017], masks[2051], resolution_m=10.0)

    # Generate updated verdict.json
    new_verdict = generate_verdict(new_timeseries, zone_key, cropland_loss_ha=loss_ha)
    verdict_path = zone_dir / "verdict.json"
    with open(verdict_path, "w") as f:
        json.dump(new_verdict, f, indent=2)

    logger.info(
        f"  2051 U-Net Verdict updated: Grade {new_verdict['grade']} (ABI={new_verdict['abi']:.3f}, Crop Loss={loss_ha:.1f} ha)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run spatial land-cover forecasting using U-Net")
    parser.add_argument(
        "--load-path",
        type=str,
        default="model/checkpoints/unet_weights.pt",
        help="Path to trained U-Net checkpoint file",
    )
    parser.add_argument("--zone", type=str, default="all", help="Specific zone key to forecast, or 'all'")
    parser.add_argument("--batch-size", type=int, default=None, help="Batch size")
    args = parser.parse_args()

    # Detect device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cpu":
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        logger.info("ENVIRONMENT: Local CPU detected.")
    else:
        logger.info("ENVIRONMENT: GPU detected.")

    # Load configuration
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    all_zones = cfg.get("zones", {})
    if args.zone != "all":
        if args.zone not in all_zones:
            logger.error(f"Zone '{args.zone}' not found in configuration.")
            sys.exit(1)
        zone_keys = [args.zone]
    else:
        zone_keys = sorted(list(all_zones.keys()))

    # Build model and load weights
    model = UNet(in_channels=22, out_channels=6).to(device)
    load_path = Path(args.load_path)
    if not load_path.exists():
        logger.error(f"Trained checkpoint weights file not found at: {load_path}")
        logger.error("Please run the training script first: python scripts/train_unet.py")
        sys.exit(1)

    model.load_state_dict(torch.load(load_path, map_location=device))
    model.eval()
    logger.info(f"Loaded trained U-Net model checkpoint from: {load_path}")

    # Set parameters depending on hardware/cli arguments
    cpu_cores = os.cpu_count() or 2
    if device.type == "cuda":
        batch_size = args.batch_size or 128
        num_workers = min(2, cpu_cores)
        pin_memory = True
        use_amp = True
    else:
        batch_size = args.batch_size or 8
        num_workers = 0
        pin_memory = False
        use_amp = False

    # 1. Run validation step on all zones (2019 & 2021 -> 2023 target)
    logger.info("\nEvaluating Global U-Net validation accuracy on 2023 targets...")
    val_dataset = GlobalPatchDataset(zone_keys, 2019, 2021, 2023, patch_size=128, augment=False)
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory,
    )

    correct = 0
    total = 0
    with torch.no_grad():
        for X_batch, y_batch, prev_batch in val_loader:
            X_batch, y_batch, prev_batch = X_batch.to(device), y_batch.to(device), prev_batch.to(device)
            with torch.amp.autocast("cuda", enabled=use_amp):
                outputs = model(X_batch)
                # Apply transition constraints by masking logits
                allowed_tensor = torch.tensor(ALLOWED_TRANSITIONS, device=device, dtype=torch.bool)
                mask = allowed_tensor[prev_batch].permute(0, 3, 1, 2)
                outputs_masked = outputs.clone()
                outputs_masked[~mask] = -1e9
                preds = torch.argmax(outputs_masked, dim=1)

            correct += (preds == y_batch).sum().item()
            total += y_batch.numel()

    acc = (correct / total) * 100 if total > 0 else 0.0
    logger.info(f"Global U-Net 2023 Validation Pixel Accuracy: {acc:.2f}%")

    # 2. Run recursive forecasting for each zone
    for zone_key in zone_keys:
        logger.info("\n" + "=" * 50)
        logger.info(f"Running U-Net forecasting up to 2051 for: {zone_key}")
        forecast_zone(zone_key, model, device, batch_size, num_workers, pin_memory, use_amp)

    logger.info("\nAll zones successfully forecasted.")


if __name__ == "__main__":
    main()
