"""
scratch/unet_forecast_prototype.py

Implements a lightweight PyTorch U-Net for spatial land-cover forecasting.
Loops over all agricultural zones, trains a convolutional neural network (CNN) on CPU,
forecasts 2025, and updates the dashboard assets.
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

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))
from analytics.abi import compute_abi, compute_cropland_loss_ha
from analytics.grader import generate_verdict

# Optimize CPU threads for PyTorch to prevent Mac overheating
torch.set_num_threads(2)
torch.set_num_interop_threads(1)
import gc

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
PRECOMPUTED_DIR = PROJECT_ROOT / "demo" / "precomputed"
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"

CLASS_COLORS = {
    0: (0, 0, 0),
    1: (220, 38, 38),
    2: (130, 90, 44),
    3: (212, 160, 23),
    4: (34, 139, 34),
    5: (30, 100, 200),
    6: (210, 180, 140),
}

def rgb_to_mask(rgb_img):
    h, w = rgb_img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for cls_id, color in CLASS_COLORS.items():
        match = np.all(rgb_img == color, axis=-1)
        mask[match] = cls_id
    return mask

def mask_to_rgb(mask):
    h, w = mask.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for cls_id, color in CLASS_COLORS.items():
        rgb[mask == cls_id] = color
    return rgb

# ─────────────────────────────────────────────────────
# 1. U-Net Architecture (Lightweight)
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

class MiniUNet(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.inc = DoubleConv(in_channels, 32)
        self.down1 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(32, 64))
        self.down2 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(64, 128))
        
        self.up1 = nn.ConvTranspose2d(128, 64, 2, stride=2)
        self.conv1 = DoubleConv(128, 64)
        self.up2 = nn.ConvTranspose2d(64, 32, 2, stride=2)
        self.conv2 = DoubleConv(64, 32)
        
        self.outc = nn.Conv2d(32, out_channels, 1)

    def forward(self, x):
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        
        up1 = self.up1(x3)
        x_up1 = torch.cat([up1, x2], dim=1)
        conv1 = self.conv1(x_up1)
        
        up2 = self.up2(conv1)
        x_up2 = torch.cat([up2, x1], dim=1)
        conv2 = self.conv2(x_up2)
        
        return self.outc(conv2)

# ─────────────────────────────────────────────────────
# 2. PyTorch Dataset & Chunker
# ─────────────────────────────────────────────────────

class PatchDataset(Dataset):
    def __init__(self, mask_prev2, mask_prev, mask_target=None, patch_size=128):
        self.patch_size = patch_size
        h, w = mask_prev.shape
        self.h_patches = h // patch_size
        self.w_patches = w // patch_size
        
        h_crop = self.h_patches * patch_size
        w_crop = self.w_patches * patch_size
        
        self.mask_prev2 = mask_prev2[:h_crop, :w_crop]
        self.mask_prev = mask_prev[:h_crop, :w_crop]
        self.mask_target = mask_target[:h_crop, :w_crop] if mask_target is not None else None

    def __len__(self):
        return self.h_patches * self.w_patches

    def __getitem__(self, idx):
        py = idx // self.w_patches
        px = idx % self.w_patches
        y = py * self.patch_size
        x = px * self.patch_size
        
        patch_prev2 = self.mask_prev2[y:y+self.patch_size, x:x+self.patch_size]
        patch_prev  = self.mask_prev[y:y+self.patch_size, x:x+self.patch_size]
        
        prev2_oh = np.eye(7)[patch_prev2].transpose(2, 0, 1).astype(np.float32)
        prev_oh  = np.eye(7)[patch_prev].transpose(2, 0, 1).astype(np.float32)
        X = np.concatenate([prev2_oh, prev_oh], axis=0)
        
        if self.mask_target is not None:
            patch_target = self.mask_target[y:y+self.patch_size, x:x+self.patch_size]
            return torch.tensor(X), torch.tensor(patch_target, dtype=torch.long)
        return torch.tensor(X)

# ─────────────────────────────────────────────────────
# 3. Forecast Zone Function
# ─────────────────────────────────────────────────────

def forecast_zone(zone_key, zone_cfg):
    zone_dir = PRECOMPUTED_DIR / zone_key
    if not zone_dir.exists():
        logger.warning(f"Zone {zone_key} directory not found. Skipping.")
        return

    logger.info(f"\n==================================================")
    logger.info(f"U-Net Spatial Growth Forecasting for: {zone_key}")

    # Load masks
    masks = {}
    for yr in [2017, 2019, 2021, 2023]:
        img = np.array(Image.open(zone_dir / f"mask_rgb_{yr}.png"))
        masks[yr] = rgb_to_mask(img)

    h, w = masks[2017].shape

    # Prepare Training DataLoader (2017 + 2019 -> 2021)
    train_dataset = PatchDataset(masks[2017], masks[2019], masks[2021], patch_size=128)
    train_loader = DataLoader(train_dataset, batch_size=4, shuffle=True)

    # Build and train U-Net
    model = MiniUNet(in_channels=14, out_channels=7)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.005)

    model.train()
    for epoch in range(3):
        epoch_loss = 0.0
        for X_batch, y_batch in train_loader:
            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item() * X_batch.size(0)
        logger.info(f"  Epoch {epoch+1}/3 | Loss: {epoch_loss/len(train_dataset):.4f}")

    # Validate on 2023
    val_dataset = PatchDataset(masks[2019], masks[2021], masks[2023], patch_size=128)
    val_loader = DataLoader(val_dataset, batch_size=4, shuffle=False)
    
    model.eval()
    correct = 0
    total = 0
    with torch.no_grad():
        for X_batch, y_batch in val_loader:
            outputs = model(X_batch)
            preds = torch.argmax(outputs, dim=1)
            correct += (preds == y_batch).sum().item()
            total += y_batch.numel()
    
    acc = correct / total * 100
    logger.info(f"  U-Net 2023 Validation Pixel Accuracy: {acc:.2f}%")

    # Forecast 2025
    forecast_dataset = PatchDataset(masks[2021], masks[2023], patch_size=128)
    forecast_loader = DataLoader(forecast_dataset, batch_size=4, shuffle=False)
    
    h_crop = forecast_dataset.h_patches * 128
    w_crop = forecast_dataset.w_patches * 128
    forecast_mask = np.zeros((h_crop, w_crop), dtype=np.uint8)

    patch_idx = 0
    with torch.no_grad():
        for X_batch in forecast_loader:
            outputs = model(X_batch)
            preds = torch.argmax(outputs, dim=1).cpu().numpy()
            
            for b in range(preds.shape[0]):
                py = patch_idx // forecast_dataset.w_patches
                px = patch_idx % forecast_dataset.w_patches
                y = py * 128
                x = px * 128
                forecast_mask[y:y+128, x:x+128] = preds[b]
                patch_idx += 1

    # Pad back to original dimensions
    full_forecast_mask = np.zeros((h, w), dtype=np.uint8)
    full_forecast_mask[:h_crop, :w_crop] = forecast_mask
    if h > h_crop:
        full_forecast_mask[h_crop:, :] = 6
    if w > w_crop:
        full_forecast_mask[:, w_crop:] = 6

    # Save mask_rgb_2025.png
    forecast_rgb = mask_to_rgb(full_forecast_mask)
    output_path = zone_dir / "mask_rgb_2025.png"
    Image.fromarray(forecast_rgb).save(output_path)
    logger.info(f"  Saved predicted mask: {output_path.name}")

    # Calculate 2025 stats
    stats = compute_abi(full_forecast_mask)
    stats["year"] = 2025
    stats["soil_pixels"] = int((full_forecast_mask == 6).sum())
    stats["soil_pct"] = round(stats["soil_pixels"] / full_forecast_mask.size * 100, 2)
    stats["buildings_pct"] = round(stats["buildings_pixels"] / full_forecast_mask.size * 100, 2)
    stats["roads_pct"] = round(stats["roads_pixels"] / full_forecast_mask.size * 100, 2)
    stats["vegetation_pct"] = round(stats["vegetation_pixels"] / full_forecast_mask.size * 100, 2)
    stats["water_pct"] = round(stats["water_pixels"] / full_forecast_mask.size * 100, 2)
    stats["cropland_pct"] = round(stats["cropland_pixels"] / full_forecast_mask.size * 100, 2)

    # Load and update verdict.json
    verdict_path = zone_dir / "verdict.json"
    with open(verdict_path) as f:
        verdict = json.load(f)

    timeseries = verdict.get("timeseries", [])
    timeseries = [r for r in timeseries if r["year"] != 2025]
    timeseries.append(stats)
    timeseries = sorted(timeseries, key=lambda x: x["year"])

    loss_ha = compute_cropland_loss_ha(masks[2017], full_forecast_mask, resolution_m=10.0)
    new_verdict = generate_verdict(timeseries, zone_key, cropland_loss_ha=loss_ha)
    
    with open(verdict_path, "w") as f:
        json.dump(new_verdict, f, indent=2)
    
    logger.info(f"  2025 U-Net Verdict: Grade {new_verdict['grade']} (ABI={new_verdict['abi']:.3f}, Crop Loss={loss_ha:.1f} ha)")
    
    # Force garbage collection to free CPU memory
    del model, train_loader, val_loader, forecast_loader
    gc.collect()

if __name__ == "__main__":
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    
    zones = cfg.get("zones", {})
    for zone_key, zone_cfg in sorted(zones.items()):
        forecast_zone(zone_key, zone_cfg)
    
    logger.info("\nAll zones successfully forecasted using U-Net.")
