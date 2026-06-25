"""
scratch/unet_forecast_prototype.py

Implements an optimized PyTorch U-Net for spatial land-cover forecasting.
Trains a single global convolutional neural network (CNN) on multi-spectral features,
evaluates validation accuracy on 2023, forecasts 2025, and updates the dashboard assets.
Adjusts execution settings dynamically for Mac (CPU thermal control) and Colab (T4 GPU performance).
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
import yaml
import sys
import json
import logging
from pathlib import Path
from PIL import Image
from scipy.ndimage import distance_transform_edt

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG_PATH, PRECOMPUTED_DIR
from core.class_map import CLASS_COLORS
from core.image_utils import mask_to_rgb, rgb_to_mask
from analytics.abi import compute_abi, compute_cropland_loss_ha
from analytics.grader import generate_verdict

# Detect device & optimize CPU threads if running on CPU (to prevent Mac overheating)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
if device.type == "cpu":
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
import gc

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Allowed transition matrix: [from_class, to_class]
ALLOWED_TRANSITIONS = np.array([
    [True,  True,  True,  True,  True,  True],  # 0 (bg): can stay bg or transition to anything
    [False, True,  False, False, False, False], # 1 (bld): can ONLY stay building (strict persistence)
    [False, True,  True,  False, False, True],  # 2 (crop): can become bld or soil, but NOT veg or water
    [False, True,  True,  True,  False, True],  # 3 (veg): can become bld, crop, soil, or stay veg, but NOT water
    [False, True,  True,  False, True,  True],  # 4 (wat): can become bld, crop, soil, or stay water, but NOT veg
    [False, True,  True,  False, False, True],  # 5 (soil): can become bld, crop, or stay soil, but NOT veg or water
], dtype=bool)

# ─────────────────────────────────────────────────────
# 1. U-Net Architecture (Standard 4-Level Deep)
# ─────────────────────────────────────────────────────

class DoubleConv(nn.Module):
    def __init__(self, in_ch, out_ch):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True)
        )
    def forward(self, x):
        return self.conv(x)

class UNet(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.inc = DoubleConv(in_channels, 64)
        self.down1 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(64, 128))
        self.down2 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(128, 256))
        self.down3 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(256, 512))
        
        self.up1 = nn.ConvTranspose2d(512, 256, 2, stride=2)
        self.conv1 = DoubleConv(512, 256)
        self.up2 = nn.ConvTranspose2d(256, 128, 2, stride=2)
        self.conv2 = DoubleConv(256, 128)
        self.up3 = nn.ConvTranspose2d(128, 64, 2, stride=2)
        self.conv3 = DoubleConv(128, 64)
        
        self.outc = nn.Conv2d(64, out_channels, 1)

    def forward(self, x):
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        
        up1 = self.up1(x4)
        x_up1 = torch.cat([up1, x3], dim=1)
        conv1 = self.conv1(x_up1)
        
        up2 = self.up2(conv1)
        x_up2 = torch.cat([up2, x2], dim=1)
        conv2 = self.conv2(x_up2)
        
        up3 = self.up3(conv2)
        x_up3 = torch.cat([up3, x1], dim=1)
        conv3 = self.conv3(x_up3)
        
        return self.outc(conv3)

# ─────────────────────────────────────────────────────
# 2. PyTorch Global Dataset
# ─────────────────────────────────────────────────────

def compute_distance_transforms(mask):
    """Compute normalized distance transforms for classes 1..5."""
    dists = []
    for cls_id in [1, 2, 3, 4, 5]:
        cls_mask = (mask == cls_id).astype(np.uint8)
        if cls_mask.sum() == 0:
            dist = np.full(mask.shape, 10.0, dtype=np.float32)
        else:
            dist = (distance_transform_edt(1 - cls_mask) / 100.0).astype(np.float32)
            dist = np.clip(dist, 0.0, 10.0)
        dists.append(dist)
    return np.stack(dists, axis=-1) # H x W x 5

class GlobalPatchDataset(Dataset):
    def __init__(self, zone_keys, year_prev2, year_prev, year_target=None, patch_size=128, augment=False):
        self.patch_size = patch_size
        self.augment = augment
        self.patches = []
        self.zones_data = []
        
        for zone_key in zone_keys:
            zone_dir = PRECOMPUTED_DIR / zone_key
            if not zone_dir.exists():
                continue
                
            # Load masks
            mask_prev2_path = zone_dir / f"mask_rgb_{year_prev2}.png"
            if not mask_prev2_path.exists():
                mask_prev2_path = zone_dir / "mask_rgb_2023.png"
            mask_prev2_rgb = np.array(Image.open(mask_prev2_path))
            mask_prev2 = rgb_to_mask(mask_prev2_rgb)
            
            mask_prev_path = zone_dir / f"mask_rgb_{year_prev}.png"
            if not mask_prev_path.exists():
                mask_prev_path = zone_dir / "mask_rgb_2023.png"
            mask_prev_rgb = np.array(Image.open(mask_prev_path))
            mask_prev = rgb_to_mask(mask_prev_rgb)
            
            mask_target = None
            if year_target is not None:
                mask_target_path = zone_dir / f"mask_rgb_{year_target}.png"
                if not mask_target_path.exists():
                    mask_target_path = zone_dir / "mask_rgb_2023.png"
                mask_target_rgb = np.array(Image.open(mask_target_path))
                mask_target = rgb_to_mask(mask_target_rgb)
                
            h, w = mask_prev.shape
            
            # Pad dimensions to next multiple of patch_size using edge padding
            pad_h = (patch_size - (h % patch_size)) % patch_size
            pad_w = (patch_size - (w % patch_size)) % patch_size
            
            mask_prev2 = np.pad(mask_prev2, ((0, pad_h), (0, pad_w)), mode="edge")
            mask_prev = np.pad(mask_prev, ((0, pad_h), (0, pad_w)), mode="edge")
            if mask_target is not None:
                mask_target = np.pad(mask_target, ((0, pad_h), (0, pad_w)), mode="edge")
                
            h_patches = (h + pad_h) // patch_size
            w_patches = (w + pad_w) // patch_size
            
            # Compute distance transforms on padded masks
            dist_prev2 = compute_distance_transforms(mask_prev2)
            dist_prev = compute_distance_transforms(mask_prev)
            
            # Load spectral features (NDVI + RGB) for year_prev2
            ndvi_img_prev2_path = zone_dir / f"ndvi_map_{year_prev2}.png"
            if not ndvi_img_prev2_path.exists():
                ndvi_img_prev2_path = zone_dir / "ndvi_map_2023.png"
            ndvi_img_prev2 = Image.open(ndvi_img_prev2_path).convert("L")
            if ndvi_img_prev2.size != (w, h):
                ndvi_img_prev2 = ndvi_img_prev2.resize((w, h), Image.Resampling.BILINEAR)
            ndvi_arr_prev2 = np.array(ndvi_img_prev2, dtype=np.float32) / 255.0
            ndvi_arr_prev2 = np.pad(ndvi_arr_prev2, ((0, pad_h), (0, pad_w)), mode="edge")
            
            tc_img_prev2_path = zone_dir / f"true_color_{year_prev2}.png"
            if not tc_img_prev2_path.exists():
                tc_img_prev2_path = zone_dir / "true_color_2023.png"
            tc_img_prev2 = Image.open(tc_img_prev2_path).convert("RGB")
            if tc_img_prev2.size != (w, h):
                tc_img_prev2 = tc_img_prev2.resize((w, h), Image.Resampling.BILINEAR)
            tc_arr_prev2 = np.array(tc_img_prev2, dtype=np.float32) / 255.0
            tc_arr_prev2 = np.pad(tc_arr_prev2, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
            
            # Load spectral features (NDVI + RGB) for year_prev
            ndvi_img_prev_path = zone_dir / f"ndvi_map_{year_prev}.png"
            if not ndvi_img_prev_path.exists():
                ndvi_img_prev_path = zone_dir / "ndvi_map_2023.png"
            ndvi_img_prev = Image.open(ndvi_img_prev_path).convert("L")
            if ndvi_img_prev.size != (w, h):
                ndvi_img_prev = ndvi_img_prev.resize((w, h), Image.Resampling.BILINEAR)
            ndvi_arr_prev = np.array(ndvi_img_prev, dtype=np.float32) / 255.0
            ndvi_arr_prev = np.pad(ndvi_arr_prev, ((0, pad_h), (0, pad_w)), mode="edge")
            
            tc_img_prev_path = zone_dir / f"true_color_{year_prev}.png"
            if not tc_img_prev_path.exists():
                tc_img_prev_path = zone_dir / "true_color_2023.png"
            tc_img_prev = Image.open(tc_img_prev_path).convert("RGB")
            if tc_img_prev.size != (w, h):
                tc_img_prev = tc_img_prev.resize((w, h), Image.Resampling.BILINEAR)
            tc_arr_prev = np.array(tc_img_prev, dtype=np.float32) / 255.0
            tc_arr_prev = np.pad(tc_arr_prev, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
            
            # Save full arrays for dynamic cropping during training
            if self.augment:
                self.zones_data.append({
                    "mask_prev2": mask_prev2,
                    "mask_prev": mask_prev,
                    "dist_prev2": dist_prev2,
                    "dist_prev": dist_prev,
                    "ndvi_prev2": ndvi_arr_prev2,
                    "rgb_prev2": tc_arr_prev2,
                    "ndvi_prev": ndvi_arr_prev,
                    "rgb_prev": tc_arr_prev,
                    "mask_target": mask_target,
                    "h_pad": h + pad_h,
                    "w_pad": w + pad_w
                })
            
            # Build fixed grid patches
            for py in range(h_patches):
                for px in range(w_patches):
                    y = py * patch_size
                    x = px * patch_size
                    
                    p_mask_prev2 = mask_prev2[y:y+patch_size, x:x+patch_size]
                    p_mask_prev = mask_prev[y:y+patch_size, x:x+patch_size]
                    p_dist_prev2 = dist_prev2[y:y+patch_size, x:x+patch_size]
                    p_dist_prev = dist_prev[y:y+patch_size, x:x+patch_size]
                    p_ndvi_prev2 = ndvi_arr_prev2[y:y+patch_size, x:x+patch_size]
                    p_rgb_prev2 = tc_arr_prev2[y:y+patch_size, x:x+patch_size]
                    p_ndvi_prev = ndvi_arr_prev[y:y+patch_size, x:x+patch_size]
                    p_rgb_prev = tc_arr_prev[y:y+patch_size, x:x+patch_size]
                    
                    p_target = None
                    if mask_target is not None:
                        p_target = mask_target[y:y+patch_size, x:x+patch_size]
                        
                    self.patches.append({
                        "prev2": p_mask_prev2,
                        "prev": p_mask_prev,
                        "dist_prev2": p_dist_prev2,
                        "dist_prev": p_dist_prev,
                        "ndvi_prev2": p_ndvi_prev2,
                        "rgb_prev2": p_rgb_prev2,
                        "ndvi_prev": p_ndvi_prev,
                        "rgb_prev": p_rgb_prev,
                        "target": p_target
                    })
                    
        if self.augment:
            self.length = len(zone_keys) * 150
            self.h_patches = None
            self.w_patches = None
        else:
            self.h_patches = h_patches
            self.w_patches = w_patches

    def __len__(self):
        if self.augment:
            return self.length
        return len(self.patches)

    def __getitem__(self, idx):
        if self.augment:
            # Dynamic random cropping from a random zone
            zone_idx = idx % len(self.zones_data)
            zone = self.zones_data[zone_idx]
            h_pad, w_pad = zone["h_pad"], zone["w_pad"]
            
            # Crop coordinates
            y = np.random.randint(0, h_pad - self.patch_size + 1)
            x = np.random.randint(0, w_pad - self.patch_size + 1)
            
            p_prev2 = zone["mask_prev2"][y:y+self.patch_size, x:x+self.patch_size]
            p_prev = zone["mask_prev"][y:y+self.patch_size, x:x+self.patch_size]
            p_dist_prev2 = zone["dist_prev2"][y:y+self.patch_size, x:x+self.patch_size]
            p_dist_prev = zone["dist_prev"][y:y+self.patch_size, x:x+self.patch_size]
            p_ndvi_prev2 = zone["ndvi_prev2"][y:y+self.patch_size, x:x+self.patch_size]
            p_rgb_prev2 = zone["rgb_prev2"][y:y+self.patch_size, x:x+self.patch_size]
            p_ndvi_prev = zone["ndvi_prev"][y:y+self.patch_size, x:x+self.patch_size]
            p_rgb_prev = zone["rgb_prev"][y:y+self.patch_size, x:x+self.patch_size]
            
            p_target = None
            if zone["mask_target"] is not None:
                p_target = zone["mask_target"][y:y+self.patch_size, x:x+self.patch_size]
                
            # Apply augmentations (flips & rotations)
            if np.random.rand() > 0.5:
                p_prev2 = np.fliplr(p_prev2)
                p_prev = np.fliplr(p_prev)
                p_dist_prev2 = np.fliplr(p_dist_prev2)
                p_dist_prev = np.fliplr(p_dist_prev)
                p_ndvi_prev2 = np.fliplr(p_ndvi_prev2)
                p_rgb_prev2 = np.fliplr(p_rgb_prev2)
                p_ndvi_prev = np.fliplr(p_ndvi_prev)
                p_rgb_prev = np.fliplr(p_rgb_prev)
                if p_target is not None:
                    p_target = np.fliplr(p_target)
            if np.random.rand() > 0.5:
                p_prev2 = np.flipud(p_prev2)
                p_prev = np.flipud(p_prev)
                p_dist_prev2 = np.flipud(p_dist_prev2)
                p_dist_prev = np.flipud(p_dist_prev)
                p_ndvi_prev2 = np.flipud(p_ndvi_prev2)
                p_rgb_prev2 = np.flipud(p_rgb_prev2)
                p_ndvi_prev = np.flipud(p_ndvi_prev)
                p_rgb_prev = np.flipud(p_rgb_prev)
                if p_target is not None:
                    p_target = np.flipud(p_target)
                    
            rot_k = np.random.randint(0, 4)
            if rot_k > 0:
                p_prev2 = np.rot90(p_prev2, k=rot_k)
                p_prev = np.rot90(p_prev, k=rot_k)
                p_dist_prev2 = np.rot90(p_dist_prev2, k=rot_k)
                p_dist_prev = np.rot90(p_dist_prev, k=rot_k)
                p_ndvi_prev2 = np.rot90(p_ndvi_prev2, k=rot_k)
                p_rgb_prev2 = np.rot90(p_rgb_prev2, k=rot_k, axes=(0, 1))
                p_ndvi_prev = np.rot90(p_ndvi_prev, k=rot_k)
                p_rgb_prev = np.rot90(p_rgb_prev, k=rot_k, axes=(0, 1))
                if p_target is not None:
                    p_target = np.rot90(p_target, k=rot_k)
        else:
            # Fixed grid patch
            patch = self.patches[idx]
            p_prev2 = patch["prev2"]
            p_prev = patch["prev"]
            p_dist_prev2 = patch["dist_prev2"]
            p_dist_prev = patch["dist_prev"]
            p_ndvi_prev2 = patch["ndvi_prev2"]
            p_rgb_prev2 = patch["rgb_prev2"]
            p_ndvi_prev = patch["ndvi_prev"]
            p_rgb_prev = patch["rgb_prev"]
            p_target = patch["target"]
            
        # One-hot representations
        prev2_oh = np.eye(6)[p_prev2].transpose(2, 0, 1).astype(np.float32)
        prev_oh  = np.eye(6)[p_prev].transpose(2, 0, 1).astype(np.float32)
        dist_feat_prev = p_dist_prev.transpose(2, 0, 1)   # 5 x H x W
        # Compute change velocity in distance transforms (spatial change features)
        dist_diff = (p_dist_prev - p_dist_prev2).transpose(2, 0, 1) # 5 x H x W
        
        X = np.concatenate([
            prev2_oh, prev_oh,
            dist_feat_prev, dist_diff
        ], axis=0) # 22 channels
        
        if p_target is not None:
            return (torch.tensor(X.copy(), dtype=torch.float32), 
                    torch.tensor(p_target.copy(), dtype=torch.long),
                    torch.tensor(p_prev.copy(), dtype=torch.long))
        return (torch.tensor(X.copy(), dtype=torch.float32),
                torch.tensor(p_prev.copy(), dtype=torch.long))

def compute_class_weights(dataset):
    """Calculate inverse frequency weights for class imbalance."""
    counts = np.zeros(6, dtype=np.int64)
    for p in dataset.patches:
        if p["target"] is not None:
            counts += np.bincount(p["target"].flatten(), minlength=6)
    total = counts.sum()
    if total == 0:
        return torch.ones(6, dtype=torch.float32)
    raw_weights = total / (len(counts) * (counts + 1e-5))
    # Cap weights to avoid rare classes (like class 0) zeroing out others
    capped_weights = np.clip(raw_weights, a_min=0.1, a_max=10.0)
    normalized_weights = capped_weights / capped_weights.sum() * 6.0
    return torch.tensor(normalized_weights, dtype=torch.float32)

class DiceLoss(nn.Module):
    """Multi-class Dice Loss to directly optimize region overlap."""
    def __init__(self, smooth=1.0):
        super().__init__()
        self.smooth = smooth

    def forward(self, logits, targets):
        num_classes = logits.size(1)
        probs = torch.softmax(logits, dim=1)
        
        # Convert targets to one-hot: (N, C, H, W)
        targets_one_hot = torch.zeros_like(logits)
        targets_one_hot.scatter_(1, targets.unsqueeze(1), 1)
        
        dice = 0.0
        for c in range(num_classes):
            p_c = probs[:, c, :, :]
            t_c = targets_one_hot[:, c, :, :]
            intersection = (p_c * t_c).sum()
            union = p_c.sum() + t_c.sum()
            dice_c = (2.0 * intersection + self.smooth) / (union + self.smooth)
            dice += dice_c
            
        return 1.0 - (dice / num_classes)

class HybridLoss(nn.Module):
    """Dice + Cross-Entropy Loss."""
    def __init__(self, weight=None, smooth=1.0):
        super().__init__()
        self.ce = nn.CrossEntropyLoss(weight=weight)
        self.dice = DiceLoss(smooth=smooth)

    def forward(self, logits, targets):
        return 0.5 * self.ce(logits, targets) + 0.5 * self.dice(logits, targets)

class ChangeWeightedHybridLoss(nn.Module):
    """Dice + Change-Weighted Cross-Entropy Loss."""
    def __init__(self, change_weight=3.0, smooth=1.0):
        super().__init__()
        self.change_weight = change_weight
        self.ce = nn.CrossEntropyLoss(reduction="none")
        self.dice = DiceLoss(smooth=smooth)

    def forward(self, logits, targets, prev):
        # CE loss (unreduced)
        ce_loss = self.ce(logits, targets) # (N, H, W)
        
        # Calculate pixel-wise weights based on whether they transitioned
        change_mask = (targets != prev)
        weights = torch.ones_like(targets, dtype=torch.float32)
        weights[change_mask] = self.change_weight
        
        weighted_ce = (ce_loss * weights).mean()
        dice_loss = self.dice(logits, targets)
        
        return 0.5 * weighted_ce + 0.5 * dice_loss

# ─────────────────────────────────────────────────────
# 3. Main Global Orchestration
# ─────────────────────────────────────────────────────

if __name__ == "__main__":
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    
    zones = cfg.get("zones", {})
    zone_keys = sorted(list(zones.keys()))
    
    logger.info("Initializing global model dataset...")
    # Load consolidated data from all zones (2017 & 2019 -> 2021 target)
    train_dataset = GlobalPatchDataset(zone_keys, 2017, 2019, 2021, patch_size=128, augment=True)
    
    # Platform-specific optimization adjustments
    import os
    cpu_cores = os.cpu_count() or 2
    if device.type == "cuda":
        batch_size = 128
        num_workers = min(2, cpu_cores)  # Limit workers to avoid warnings/slowness on Colab VM
        pin_memory = True
        epochs = 50
        use_amp = True
        logger.info("ENVIRONMENT: Google Colab T4 GPU detected.")
        logger.info(f"PROFILING: Maximum hardware settings active (batch=128, workers={num_workers}, AMP mixed-precision=ON)")
    else:
        batch_size = 8
        num_workers = 0
        pin_memory = False
        epochs = 5
        use_amp = False
        logger.info("ENVIRONMENT: Local macOS CPU detected.")
        logger.info("PROFILING: Thermal-aware settings active (batch=8, workers=0, restricted threads)")
        
    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin_memory
    )
    
    # Compute inverse frequency weights
    class_weights = compute_class_weights(train_dataset).to(device)
    logger.info(f"Class-imbalance weights: {class_weights.cpu().numpy()}")
    
    # Build U-Net model with 22 input channels (one-hot masks + Distance Transforms for both years)
    model = UNet(in_channels=22, out_channels=6).to(device)
    # Use Change-Weighted Hybrid Loss to focus on transitions and region overlap
    criterion = ChangeWeightedHybridLoss(change_weight=3.0)
    optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4)
    # Cosine Annealing Learning Rate Scheduler for smooth convergence
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    scaler = torch.amp.GradScaler('cuda', enabled=use_amp)
    
    # Train Loop
    logger.info(f"\nTraining Global U-Net model for {epochs} epochs...")
    model.train()
    for epoch in range(epochs):
        epoch_loss = 0.0
        for X_batch, y_batch, prev_batch in train_loader:
            X_batch, y_batch, prev_batch = X_batch.to(device), y_batch.to(device), prev_batch.to(device)
            optimizer.zero_grad()
            with torch.amp.autocast('cuda', enabled=use_amp):
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch, prev_batch)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            epoch_loss += loss.item() * X_batch.size(0)
        scheduler.step() # Decay learning rate
        logger.info(f"  Epoch {epoch+1}/{epochs} | Loss: {epoch_loss/len(train_dataset):.4f} | LR: {scheduler.get_last_lr()[0]:.6f}")
        
    # Validation step on all zones (2019 & 2021 -> 2023 target)
    logger.info("\nEvaluating Global U-Net on 2023 Validation targets...")
    val_dataset = GlobalPatchDataset(zone_keys, 2019, 2021, 2023, patch_size=128, augment=False)
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin_memory
    )
    
    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for X_batch, y_batch, prev_batch in val_loader:
            X_batch, y_batch, prev_batch = X_batch.to(device), y_batch.to(device), prev_batch.to(device)
            with torch.amp.autocast('cuda', enabled=use_amp):
                outputs = model(X_batch)
                
                # Apply transition constraints by masking logits
                allowed_tensor = torch.tensor(ALLOWED_TRANSITIONS, device=device, dtype=torch.bool)
                mask = allowed_tensor[prev_batch].permute(0, 3, 1, 2)
                outputs_masked = outputs.clone()
                outputs_masked[~mask] = -1e9
                preds = torch.argmax(outputs_masked, dim=1)
                
            correct += (preds == y_batch).sum().item()
            total += y_batch.numel()
    acc = correct / total * 100
    logger.info(f"Global U-Net 2023 Validation Pixel Accuracy: {acc:.2f}%")
    
    # Forecast up to 2051 masks recursively for all zones
    forecast_years = [2025, 2027, 2029, 2031, 2033, 2035, 2037, 2039, 2041, 2043, 2045, 2047, 2049, 2051]
    
    for zone_key in zone_keys:
        logger.info(f"\n==================================================")
        logger.info(f"U-Net Spatial Growth Forecasting up to 2051 for: {zone_key}")
        zone_dir = PRECOMPUTED_DIR / zone_key
        
        # Load masks
        masks = {}
        for yr in [2017, 2019, 2021, 2023]:
            img = np.array(Image.open(zone_dir / f"mask_rgb_{yr}.png"))
            masks[yr] = rgb_to_mask(img)
            
        h, w = masks[2017].shape
        
        for target_yr in forecast_years:
            y_prev = target_yr - 2
            y_prev2 = target_yr - 4
            
            # Sliced patch dataset for single year forecasting
            forecast_dataset = GlobalPatchDataset([zone_key], y_prev2, y_prev, None, patch_size=128, augment=False)
            forecast_loader = DataLoader(
                forecast_dataset,
                batch_size=batch_size,
                shuffle=False,
                num_workers=num_workers,
                pin_memory=pin_memory
            )
            
            h_crop = forecast_dataset.h_patches * 128
            w_crop = forecast_dataset.w_patches * 128
            forecast_mask = np.zeros((h_crop, w_crop), dtype=np.uint8)
            
            patch_idx = 0
            with torch.no_grad():
                for X_batch, prev_batch in forecast_loader:
                    X_batch, prev_batch = X_batch.to(device), prev_batch.to(device)
                    with torch.amp.autocast('cuda', enabled=use_amp):
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
                        forecast_mask[y:y+128, x:x+128] = preds[b]
                        patch_idx += 1
                        
            # Crop back to original dimensions
            full_forecast_mask = forecast_mask[:h, :w]
            
            # Apply building persistence constraint from y_prev (water shrinks naturally)
            prev_mask = masks[y_prev]
            full_forecast_mask[prev_mask == 1] = 1
            
            masks[target_yr] = full_forecast_mask
            
            # Save mask_rgb_{target_yr}.png
            forecast_rgb = mask_to_rgb(full_forecast_mask)
            output_path = zone_dir / f"mask_rgb_{target_yr}.png"
            Image.fromarray(forecast_rgb).save(output_path)
            logger.info(f"  Saved predicted mask for {target_yr}: {output_path.name}")
            
        # Rebuild timeseries for all years (historical + forecast)
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
        
        # Cropland loss (overall loss from 2017 to 2051)
        loss_ha = compute_cropland_loss_ha(masks[2017], masks[2051], resolution_m=10.0)
        
        # Grader verdict
        new_verdict = generate_verdict(new_timeseries, zone_key, cropland_loss_ha=loss_ha)
        
        verdict_path = zone_dir / "verdict.json"
        with open(verdict_path, "w") as f:
            json.dump(new_verdict, f, indent=2)
            
        logger.info(f"  2051 U-Net Verdict: Grade {new_verdict['grade']} (ABI={new_verdict['abi']:.3f}, Crop Loss={loss_ha:.1f} ha)")
        
    logger.info("\nAll zones successfully forecasted using U-Net.")
    
    # Free memory
    del model, train_loader, val_loader
    gc.collect()
