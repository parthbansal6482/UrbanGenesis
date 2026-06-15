import numpy as np
import os
from pathlib import Path
from PIL import Image
from scipy.ndimage import distance_transform_edt
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
PRECOMPUTED_DIR = PROJECT_ROOT / "demo" / "precomputed"
ZONE = "hubli_outskirts"
ZONE_DIR = PRECOMPUTED_DIR / ZONE

# Colors to map back to classes
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
    """Generate distance-to-infrastructure features using Euclidean Distance Transform."""
    features = []
    
    # 1. Distance to buildings (class 1)
    buildings = (mask == 1).astype(np.uint8)
    dist_buildings = distance_transform_edt(1 - buildings)
    features.append(dist_buildings)
    
    # 2. Distance to cropland (class 2) - captures farming boundaries
    crops = (mask == 2).astype(np.uint8)
    dist_crops = distance_transform_edt(1 - crops)
    features.append(dist_crops)
    
    return features

print(f"Loading masks for {ZONE}...")
masks = {}
for year in [2017, 2019, 2021, 2023]:
    img_path = ZONE_DIR / f"mask_rgb_{year}.png"
    if not img_path.exists():
        raise FileNotFoundError(f"Missing {img_path.name}")
    img = np.array(Image.open(img_path))
    masks[year] = rgb_to_mask(img)

h, w = masks[2017].shape
print(f"Mask size: {w}x{h}")

# Feature engineering helper
def extract_samples(year_prev2, year_prev, year_target=None):
    """Extract features for all pixels. If target is provided, returns features and labels."""
    # Base features: previous years' states
    f_prev2 = masks[year_prev2].flatten()
    f_prev = masks[year_prev].flatten()
    
    # Spatial features from the most recent year
    spatial = compute_spatial_features(masks[year_prev])
    f_spatial = [s.flatten() for s in spatial]
    
    # Stack all features
    X = np.column_stack([f_prev2, f_prev] + f_spatial)
    
    if year_target is not None:
        y = masks[year_target].flatten()
        return X, y
    return X

# 1. Training Set: use 2017 and 2019 to predict 2021
print("\nPreparing training set (predicting 2021 using 2017 + 2019)...")
X_train, y_train = extract_samples(2017, 2019, 2021)

# Subsample pixels for fast training (Random Forest can be slow on 6 million pixels)
rng = np.random.default_rng(42)
sample_indices = rng.choice(len(X_train), size=100000, replace=False)
X_train_sampled = X_train[sample_indices]
y_train_sampled = y_train[sample_indices]

# Train Classifier
print("Training Random Forest Classifier...")
clf = RandomForestClassifier(n_estimators=50, max_depth=15, random_state=42, n_jobs=-1)
clf.fit(X_train_sampled, y_train_sampled)

# 2. Validation Set: use 2019 and 2021 to predict 2023
print("\nPreparing validation set (predicting 2023 using 2019 + 2021)...")
X_val, y_val = extract_samples(2019, 2021, 2023)

print("Evaluating model performance on actual 2023 data...")
y_pred_val = clf.predict(X_val)
acc = accuracy_score(y_val, y_pred_val)
print(f"Overall Pixel Accuracy: {acc*100:.2f}%")

print("\nClassification Report (evaluating spatial predictions):")
print(classification_report(y_val, y_pred_val, labels=[0, 1, 2, 3, 4, 5, 6], target_names=[
    "background", "buildings", "roads", "cropland", "vegetation", "water", "bare_soil"
]))

# 3. Future Forecasting: use 2021 and 2023 to forecast 2025
print("\nForecasting 2025 spatial land use cover...")
X_forecast = extract_samples(2021, 2023)
y_forecast = clf.predict(X_forecast)

# Reshape back to image dimensions
forecast_mask = y_forecast.reshape((h, w))

# Calculate stats
unique, counts = np.unique(forecast_mask, return_counts=True)
stats = dict(zip(unique, counts))
print("\nPredicted 2025 Land Cover Distribution:")
for cls_id, count in stats.items():
    pct = count / forecast_mask.size * 100
    color_name = {0:"background", 1:"buildings", 2:"cropland", 3:"vegetation", 4:"water", 5:"bare_soil"}.get(cls_id)
    print(f"  {color_name}: {pct:.2f}%")

# Save predicted image
forecast_rgb = mask_to_rgb(forecast_mask)
output_path = ZONE_DIR / "mask_rgb_2025_predicted.png"
Image.fromarray(forecast_rgb).save(output_path)
print(f"\nSaved predicted 2025 map to: {output_path.name}")
