"""
scripts/forecast_unet.py

Uses a pre-trained U-Net model checkpoint to evaluate validation accuracy on 2023,
forecast future years recursively up to 2041, and generate dashboard assets.
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
from scipy.ndimage import binary_dilation, label
from torch.utils.data import DataLoader

# Setup project root path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.abi import compute_abi, compute_cropland_loss_ha
from analytics.grader import generate_verdict
from core.class_map import CLASS_COLORS
from core.config import CONFIG_PATH, PRECOMPUTED_DIR
from core.utils.image_utils import mask_to_rgb, rgb_to_mask
from model.dataset import GlobalPatchDataset, compute_distance_transforms
from model.architecture import UNet, ResNet34UNet

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


def load_model_from_checkpoint(checkpoint_path: Path, device: torch.device) -> torch.nn.Module:
    """Auto-detect model type from state_dict keys and load weights."""
    state_dict = torch.load(checkpoint_path, map_location=device)
    is_resnet = "input_projection.weight" in state_dict
    if is_resnet:
        logger.info("Auto-detected ResNet34UNet checkpoint.")
        model = ResNet34UNet(in_channels=22, out_channels=6, pretrained=False).to(device)
    else:
        logger.info("Auto-detected standard UNet checkpoint.")
        model = UNet(in_channels=22, out_channels=6).to(device)
    model.load_state_dict(state_dict)
    model.eval()
    return model


def forecast_zone(
    zone_key: str,
    model: torch.nn.Module = None,
    device: torch.device = None,
    batch_size: int = 8,
    num_workers: int = 0,
    pin_memory: bool = False,
    use_amp: bool = False,
    start_year: int = 2023,
    target_year: int = 2041,
    checkpoint_path: Path = None,
    zone_dir: Path = None,
    temperature: float = 0.8,
    confidence_threshold: float = 0.92,
) -> np.ndarray | None:
    """Run recursive spatial land-cover forecasting for a single zone."""
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if model is None:
        if checkpoint_path and Path(checkpoint_path).exists():
            model = load_model_from_checkpoint(Path(checkpoint_path), device)
        else:
            model = UNet(in_channels=22, out_channels=6).to(device)
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
    core_size = 96
    pad_h = (core_size - (h % core_size)) % core_size
    pad_w = (core_size - (w % core_size)) % core_size
    padded_shape = (h + pad_h, w + pad_w)

    # Load bbox config and compute road network proximity grid
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    zone_cfg = cfg.get("zones", {}).get(zone_key, {})
    bbox = zone_cfg.get("bbox", [0.0, 0.0, 0.0, 0.0])

    from pipeline.osm_fetcher import get_road_proximity_grid
    logger.info(f"[{zone_key}] Preparing transport corridor proximity grid for bbox {bbox}...")
    road_edt = get_road_proximity_grid(zone_key, bbox, padded_shape)
    # Exponential decay weights representing corridor influence (sigma = 15 pixels = 150m)
    road_weight = np.exp(-road_edt / 15.0)

    for step_idx, target_yr in enumerate(forecast_years):
        logger.info(f"--- Processing Year {target_yr} ---")
        y_prev = target_yr - 2
        y_prev2 = target_yr - 4

        mask_prev = masks[y_prev]
        mask_prev2 = masks[y_prev2]

        # 1. Pad masks to multiples of core_size (96) on bottom/right using edge padding
        mask_prev_padded = np.pad(mask_prev, ((0, pad_h), (0, pad_w)), mode="edge")
        mask_prev2_padded = np.pad(mask_prev2, ((0, pad_h), (0, pad_w)), mode="edge")

        # 2. Compute spatial distance features on padded masks
        logger.info(f"  [{target_yr}] Calculating Euclidean Distance Transforms (EDT) on CPU...")
        dist_prev = compute_distance_transforms(mask_prev_padded)
        dist_prev2 = compute_distance_transforms(mask_prev2_padded)

        # --- URBAN PRESSURE INJECTION (BIASED BY TRANSPORT CORRIDORS) ---
        # Problem: as buildings saturate the zone, dist_prev → 0 everywhere and
        # dist_diff → 0, meaning the model sees no spatial gradient to trigger expansion.
        # Fix: inject momentum into dist_diff that decays as building fraction saturates.
        # We bias this injection using OpenStreetMap road network proximity to pull growth along roads.
        dist_diff = (dist_prev - dist_prev2).transpose(2, 0, 1)  # 5 x H x W, raw change velocity
        bld_fraction = float((mask_prev_padded == 1).mean())
        saturation_damping = max(0.0, 1.0 - bld_fraction * 1.1)
        momentum_strength = min(0.01 * (step_idx + 1), 0.15) * saturation_damping
        
        # Pixels near roads (road_weight=1.0) receive up to 3.3x more pressure boost than remote areas.
        momentum_grid = momentum_strength * (0.3 + 0.7 * road_weight)

        # Apply only to the building class (channel 0 in dist, class id 1 in mask)
        # Negative dist_diff means buildings are getting closer → add extra negative push
        dist_diff_boosted = dist_diff.copy()
        dist_diff_boosted[0] = dist_diff_boosted[0] - momentum_grid
        logger.info(
            f"  [{target_yr}] Urban pressure momentum biased by transport corridors: max={momentum_strength:.4f} "
            f"(bld_frac={bld_fraction:.2f}, damping={saturation_damping:.2f})"
        )

        # 3. Create one-hot representations
        prev_oh = np.eye(6)[mask_prev_padded].transpose(2, 0, 1).astype(np.float32)
        prev2_oh = np.eye(6)[mask_prev2_padded].transpose(2, 0, 1).astype(np.float32)

        dist_feat_prev = dist_prev.transpose(2, 0, 1)

        # 4. Concatenate into full 22-channel feature tensor (22, H_pad, W_pad)
        # Use the pressure-boosted dist_diff instead of the raw one
        X = np.concatenate([prev2_oh, prev_oh, dist_feat_prev, dist_diff_boosted], axis=0)

        # 5. Add 16 pixels of context border padding on all 4 sides of the feature canvas
        X_padded = np.pad(X, ((0, 0), (16, 16), (16, 16)), mode="edge")

        # 6. Set up logits canvas for the padded area
        sum_logits = torch.zeros((6, h + pad_h, w + pad_w), device=device, dtype=torch.float32)

        # Convert the full padded feature canvas to a GPU tensor
        logger.info(f"  [{target_yr}] Uploading to GPU and running batched forward pass...")
        X_gpu = torch.tensor(X_padded, device=device, dtype=torch.float32)

        stride = 96  # Side-by-side stitching of the 96px cores (no overlap, no low-pass smoothing)
        coords_list = []

        for y in range(0, h + pad_h, stride):
            for x in range(0, w + pad_w, stride):
                coords_list.append((y, x))

        # Run forward pass in sub-batches of 64
        inf_batch_size = 64
        with torch.no_grad():
            for i in range(0, len(coords_list), inf_batch_size):
                batch_coords = coords_list[i : i + inf_batch_size]
                
                # Slice the 128x128 patches from X_gpu directly (using the centered coordinates)
                # Since X_gpu is padded by 16, a core coordinate (y, x) maps directly to slice [y : y + 128, x : x + 128]
                batch_patches = [X_gpu[:, y : y + 128, x : x + 128] for y, x in batch_coords]
                batch_x = torch.stack(batch_patches, dim=0)  # (SubBatch, 22, 128, 128)
                
                with torch.amp.autocast("cuda", enabled=use_amp):
                    batch_logits = model(batch_x)  # (SubBatch, 6, 128, 128)
                
                # Discard the outer 16-pixel border and paste the 96x96 central region directly
                batch_logits_cropped = batch_logits[:, :, 16:112, 16:112]  # (SubBatch, 6, 96, 96)
                
                # Paste predictions directly (no blending window needed)
                for idx, (y, x) in enumerate(batch_coords):
                    logits = batch_logits_cropped[idx]
                    sum_logits[:, y : y + 96, x : x + 96] = logits

        # 7. Apply allowed transition constraints
        prev_tensor = torch.tensor(mask_prev_padded, device=device, dtype=torch.long)
        allowed_tensor = torch.tensor(ALLOWED_TRANSITIONS, device=device, dtype=torch.bool)
        allowed_mask = allowed_tensor[prev_tensor].permute(2, 0, 1)  # (6, H_pad, W_pad)

        sum_logits[~allowed_mask] = -1e9
        
        # Deterministic argmax to get predicted classes (fully solid, no grain/speckle noise!)
        forecast_mask_padded = torch.argmax(sum_logits, dim=0).cpu().numpy().astype(np.uint8)

        # Crop back to original dimensions
        full_forecast_mask = forecast_mask_padded[:h, :w]

        # Apply building persistence constraint
        prev_mask = masks[y_prev]
        full_forecast_mask[prev_mask == 1] = 1

        # --- CONTROLLED EXPANSION SEEDING ---
        # Problem: the model's persistence bias means very few pixels at the frontier
        # get converted each step. Over 14 recursive steps this causes apparent stagnation.
        # Fix: after prediction, probabilistically seed a small fraction of pixels that are:
        #   (a) adjacent to buildings, (b) currently non-building, (c) legally convertable.
        # Seeding rate scales with saturation_damping so it naturally winds down as land runs out.
        # Base seed rate: ~0.5% of the convertable frontier per step.
        seed_rate = 0.005 * saturation_damping
        if seed_rate > 0.0001:
            building_mask = (full_forecast_mask == 1)
            # Dilate by 1 pixel to find the immediate frontier
            dilated = binary_dilation(building_mask, iterations=2)
            frontier = dilated & ~building_mask
            # Only seed legally convertable non-building classes
            convertable = np.isin(full_forecast_mask, [2, 3, 5])  # crop, veg, soil
            candidate_pixels = frontier & convertable
            candidate_indices = np.argwhere(candidate_pixels)
            n_seed = max(0, int(len(candidate_indices) * seed_rate))
            if n_seed > 0:
                chosen = candidate_indices[
                    np.random.choice(len(candidate_indices), size=n_seed, replace=False)
                ]
                full_forecast_mask[chosen[:, 0], chosen[:, 1]] = 1
                logger.info(
                    f"  [{target_yr}] Expansion seeding: converted {n_seed} frontier pixels "
                    f"to buildings (seed_rate={seed_rate:.4f}, frontier_size={len(candidate_indices)})"
                )

        masks[target_yr] = full_forecast_mask

        # For historical backtesting, we do NOT want to overwrite the zone's standard forward-looking forecast files!
        if target_yr > 2023:
            # Save predicted mask
            forecast_rgb = mask_to_rgb(full_forecast_mask)
            output_path = zone_dir / f"mask_rgb_{target_yr}.png"
            Image.fromarray(forecast_rgb).save(output_path)
            logger.info(f"  Saved U-Net forecasted mask for {target_yr}: {output_path.name}")

        # Explicitly clean up GPU memory to prevent VRAM accumulation and watchdog kills across recursive years
        del X_gpu, sum_logits, allowed_mask, prev_tensor
        if device.type == "cuda":
            torch.cuda.empty_cache()

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

    # Calculate overall cropland loss 2017 -> target_year
    loss_ha = compute_cropland_loss_ha(masks[2017], masks[target_year], resolution_m=10.0)

    # Generate updated verdict.json
    new_verdict = generate_verdict(new_timeseries, zone_key, cropland_loss_ha=loss_ha)
    verdict_path = zone_dir / "verdict.json"
    with open(verdict_path, "w") as f:
        json.dump(new_verdict, f, indent=2)

    logger.info(
        f"  {target_year} U-Net Verdict updated: Grade {new_verdict['grade']} (ABI={new_verdict['abi']:.3f}, Crop Loss={loss_ha:.1f} ha)"
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
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.8,
        help="Temperature for stochastic sampling (lower is smoother/more deterministic, higher is rougher)",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.92,
        help="Confidence threshold above which to use deterministic argmax (default: 0.92)",
    )
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
    load_path = Path(args.load_path)
    if not load_path.exists():
        logger.error(f"Trained checkpoint weights file not found at: {load_path}")
        logger.error("Please run the training script first: python scripts/train_unet.py")
        sys.exit(1)

    model = load_model_from_checkpoint(load_path, device)
    logger.info(f"Loaded trained model checkpoint from: {load_path}")

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
        logger.info(f"Running U-Net forecasting up to 2041 for: {zone_key}")
        forecast_zone(
            zone_key,
            model,
            device,
            batch_size,
            num_workers,
            pin_memory,
            use_amp,
            temperature=args.temperature,
            confidence_threshold=args.confidence_threshold,
        )

    logger.info("\nAll zones successfully forecasted.")


if __name__ == "__main__":
    main()
