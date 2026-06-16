"""
scripts/forecast_2025.py

Loads historical precomputed land use masks, trains an optimized Random Forest spatial growth model,
forecasts the 2025 classification mask, and updates verdict.json for all zones.
"""

import numpy as np
import json
import yaml
import sys
import logging
from pathlib import Path
from PIL import Image
from scipy.ndimage import distance_transform_edt
from sklearn.ensemble import RandomForestClassifier

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))
from analytics.abi import compute_abi, compute_cropland_loss_ha
from analytics.grader import generate_verdict

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
PRECOMPUTED_DIR = PROJECT_ROOT / "demo" / "precomputed"
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"

CLASS_COLORS = {
    0: (0, 0, 0),        # background - black
    1: (220, 38, 38),    # buildings - red
    2: (212, 160, 23),   # cropland - gold
    3: (34, 139, 34),    # dense vegetation - green
    4: (30, 100, 200),   # water - blue
    5: (210, 180, 140),  # bare soil - tan
}

def rgb_to_mask(rgb_img):
    """Convert RGB mask back to integer class index mask."""
    h, w = rgb_img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for cls_id, color in CLASS_COLORS.items():
        match = np.all(rgb_img == color, axis=-1)
        mask[match] = cls_id
    return mask

def mask_to_rgb(mask):
    """Convert integer class mask to RGB image for visualization."""
    h, w = mask.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for cls_id, color in CLASS_COLORS.items():
        rgb[mask == cls_id] = color
    return rgb

def compute_spatial_features(mask):
    """Generate distance features to all canonical classes using EDT."""
    features = []
    for cls_id in [1, 2, 3, 4, 5]:
        cls_mask = (mask == cls_id).astype(np.uint8)
        dist = distance_transform_edt(1 - cls_mask)
        features.append(dist)
    return features

def load_spectral_features(zone_dir, year, target_h, target_w):
    """Load and scale NDVI and True Color features, resizing if needed."""
    target_size = (target_w, target_h)
    
    # 1. Load NDVI
    ndvi_path = zone_dir / f"ndvi_map_{year}.png"
    if ndvi_path.exists():
        img = Image.open(ndvi_path).convert("L")
        if img.size != target_size:
            img = img.resize(target_size, Image.Resampling.BILINEAR)
        ndvi_arr = np.array(img, dtype=np.float32).flatten() / 255.0
    else:
        ndvi_arr = np.zeros(target_h * target_w, dtype=np.float32)
        
    # 2. Load True Color (RGB)
    tc_path = zone_dir / f"true_color_{year}.png"
    if tc_path.exists():
        img = Image.open(tc_path).convert("RGB")
        if img.size != target_size:
            img = img.resize(target_size, Image.Resampling.BILINEAR)
        tc_arr = np.array(img, dtype=np.float32) / 255.0
        r = tc_arr[:, :, 0].flatten()
        g = tc_arr[:, :, 1].flatten()
        b = tc_arr[:, :, 2].flatten()
    else:
        r = np.zeros(target_h * target_w, dtype=np.float32)
        g = np.zeros(target_h * target_w, dtype=np.float32)
        b = np.zeros(target_h * target_w, dtype=np.float32)
        
    return ndvi_arr, r, g, b

def forecast_zone(zone_key, zone_cfg):
    zone_dir = PRECOMPUTED_DIR / zone_key
    if not zone_dir.exists():
        logger.warning(f"Directory {zone_key} not found. Skipping.")
        return

    logger.info(f"\n==================================================")
    logger.info(f"Forecasting 2025 for Zone: {zone_key}")

    # Load historical masks
    masks = {}
    years = [2017, 2019, 2021, 2023]
    for yr in years:
        img_path = zone_dir / f"mask_rgb_{yr}.png"
        if not img_path.exists():
            logger.warning(f"  Missing {img_path.name}. Cannot run forecast.")
            return
        img = np.array(Image.open(img_path))
        masks[yr] = rgb_to_mask(img)

    h, w = masks[2017].shape

    # Load spectral features for input years
    ndvi_2019, r_2019, g_2019, b_2019 = load_spectral_features(zone_dir, 2019, h, w)
    ndvi_2023, r_2023, g_2023, b_2023 = load_spectral_features(zone_dir, 2023, h, w)

    # Extract training samples: predict 2021 using 2017 + 2019 + 2019 spectral features
    logger.info("  Preparing training features...")
    f_2017 = masks[2017].flatten()
    f_2019 = masks[2019].flatten()
    spatial_2019 = compute_spatial_features(masks[2019])
    flat_spatial_2019 = [s.flatten() for s in spatial_2019]
    
    X_train = np.column_stack([f_2017, f_2019] + flat_spatial_2019 + [ndvi_2019, r_2019, g_2019, b_2019])
    y_train = masks[2021].flatten()

    # Subsample for training performance
    rng = np.random.default_rng(42)
    sample_indices = rng.choice(len(X_train), size=min(100000, len(X_train)), replace=False)
    X_train_sampled = X_train[sample_indices]
    y_train_sampled = y_train[sample_indices]

    # Train Random Forest with class weighting
    logger.info("  Training Random Forest spatial growth model...")
    clf = RandomForestClassifier(n_estimators=50, max_depth=15, random_state=42, n_jobs=-1, class_weight="balanced")
    clf.fit(X_train_sampled, y_train_sampled)

    # Forecast 2025: use 2021 + 2023 + 2023 spectral features
    logger.info("  Predicting 2025 mask...")
    f_2021 = masks[2021].flatten()
    f_2023 = masks[2023].flatten()
    spatial_2023 = compute_spatial_features(masks[2023])
    flat_spatial_2023 = [s.flatten() for s in spatial_2023]
    
    X_forecast = np.column_stack([f_2021, f_2023] + flat_spatial_2023 + [ndvi_2023, r_2023, g_2023, b_2023])
    y_forecast = clf.predict(X_forecast)
    forecast_mask = y_forecast.reshape((h, w))

    # Save predicted mask_rgb_2025.png
    forecast_rgb = mask_to_rgb(forecast_mask)
    output_path = zone_dir / "mask_rgb_2025.png"
    Image.fromarray(forecast_rgb).save(output_path)
    logger.info(f"  Saved predicted mask: {output_path.name}")

    # Rebuild entire timeseries from scratch to remove road class and update indices
    new_timeseries = []
    for yr in [2017, 2019, 2021, 2023]:
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

    # Append 2025 stats
    stats = compute_abi(forecast_mask)
    stats["year"] = 2025
    stats["soil_pixels"] = int((forecast_mask == 5).sum())
    stats["soil_pct"] = round(stats["soil_pixels"] / forecast_mask.size * 100, 2)
    stats["buildings_pct"] = round(stats["buildings_pixels"] / forecast_mask.size * 100, 2)
    stats["vegetation_pct"] = round(stats["vegetation_pixels"] / forecast_mask.size * 100, 2)
    stats["water_pct"] = round(stats["water_pixels"] / forecast_mask.size * 100, 2)
    stats["cropland_pct"] = round(stats["cropland_pixels"] / forecast_mask.size * 100, 2)
    new_timeseries.append(stats)
    new_timeseries = sorted(new_timeseries, key=lambda x: x["year"])

    # Calculate cropland loss between 2017 and 2025
    loss_ha = compute_cropland_loss_ha(masks[2017], forecast_mask, resolution_m=10.0)

    # Re-run grader to generate final verdict summary
    new_verdict = generate_verdict(new_timeseries, zone_key, cropland_loss_ha=loss_ha)
    
    verdict_path = zone_dir / "verdict.json"
    with open(verdict_path, "w") as f:
        json.dump(new_verdict, f, indent=2)
    
    logger.info(f"  2025 Forecast Verdict: Grade {new_verdict['grade']} (ABI={new_verdict['abi']:.3f}, Crop Loss={loss_ha:.1f} ha)")

if __name__ == "__main__":
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    
    zones = cfg.get("zones", {})
    for zone_key, zone_cfg in zones.items():
        forecast_zone(zone_key, zone_cfg)
    
    logger.info("\nAll zones successfully forecasted for 2025.")
