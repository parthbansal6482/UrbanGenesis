"""
scratch/evaluate_accuracy.py
Calculates and prints pixel-level classification accuracy metrics for all 4 zones.
"""

import numpy as np
import yaml
import sys
from pathlib import Path
from PIL import Image
from scipy.ndimage import distance_transform_edt
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report

PROJECT_ROOT = Path(__file__).parent.parent
PRECOMPUTED_DIR = PROJECT_ROOT / "demo" / "precomputed"
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"

CLASS_COLORS = {
    0: (0, 0, 0),        # background
    1: (220, 38, 38),    # buildings
    2: (212, 160, 23),   # cropland (gold)
    3: (34, 139, 34),    # dense vegetation (green)
    4: (30, 100, 200),   # water (blue)
    5: (210, 180, 140),  # bare soil (tan)
}

def rgb_to_mask(rgb_img):
    h, w = rgb_img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for cls_id, color in CLASS_COLORS.items():
        match = np.all(rgb_img == color, axis=-1)
        mask[match] = cls_id
    return mask

def compute_spatial_features(mask):
    """Generate distance features to all canonical classes."""
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

def evaluate_zone(zone_key):
    zone_dir = PRECOMPUTED_DIR / zone_key
    if not zone_dir.exists():
        return None

    # Load masks
    masks = {}
    for yr in [2017, 2019, 2021, 2023]:
        img = np.array(Image.open(zone_dir / f"mask_rgb_{yr}.png"))
        masks[yr] = rgb_to_mask(img)

    h, w = masks[2017].shape

    # Load spectral features
    ndvi_2019, r_2019, g_2019, b_2019 = load_spectral_features(zone_dir, 2019, h, w)
    ndvi_2021, r_2021, g_2021, b_2021 = load_spectral_features(zone_dir, 2021, h, w)

    # 1. Train on 2017 + 2019 -> 2021
    f_2017 = masks[2017].flatten()
    f_2019 = masks[2019].flatten()
    spatial_2019 = compute_spatial_features(masks[2019])
    flat_spatial_2019 = [s.flatten() for s in spatial_2019]
    
    # Combine baseline mask features, multi-class distance features, and spectral features
    X_train = np.column_stack([f_2017, f_2019] + flat_spatial_2019 + [ndvi_2019, r_2019, g_2019, b_2019])
    y_train = masks[2021].flatten()

    # Sample
    rng = np.random.default_rng(42)
    sample_indices = rng.choice(len(X_train), size=min(100000, len(X_train)), replace=False)
    X_train_sampled = X_train[sample_indices]
    y_train_sampled = y_train[sample_indices]

    # Fit Random Forest with class balancing
    clf = RandomForestClassifier(n_estimators=50, max_depth=15, random_state=42, n_jobs=-1, class_weight="balanced")
    clf.fit(X_train_sampled, y_train_sampled)

    # 2. Evaluate on 2019 + 2021 -> 2023
    f_2019_val = masks[2019].flatten()
    f_2021_val = masks[2021].flatten()
    spatial_2021 = compute_spatial_features(masks[2021])
    flat_spatial_2021 = [s.flatten() for s in spatial_2021]
    
    X_val = np.column_stack([f_2019_val, f_2021_val] + flat_spatial_2021 + [ndvi_2021, r_2021, g_2021, b_2021])
    y_val = masks[2023].flatten()

    y_pred = clf.predict(X_val)
    acc = accuracy_score(y_val, y_pred)
    
    # Class-specific report
    report = classification_report(
        y_val, y_pred,
        labels=[0, 1, 2, 3, 4, 5],
        target_names=["background", "buildings", "cropland", "vegetation", "water", "bare_soil"],
        output_dict=True,
        zero_division=0
    )
    
    return acc, report

if __name__ == "__main__":
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    
    zones = cfg.get("zones", {})
    print("Evaluating prediction accuracy across all agricultural zones...\n")
    
    for zone_key in zones:
        print(f"Zone: {zone_key}...")
        try:
            acc, report = evaluate_zone(zone_key)
            print(f"  Overall Pixel Accuracy: {acc*100:.2f}%")
            print("  Key Classes:")
            for cls in ["buildings", "cropland", "vegetation", "bare_soil"]:
                metrics = report[cls]
                print(f"    - {cls.capitalize():<11}: Precision={metrics['precision']:.2f}, Recall={metrics['recall']:.2f}, F1={metrics['f1-score']:.2f}")
            print("-" * 50)
        except Exception as e:
            print(f"  Failed: {e}")
