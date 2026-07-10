"""
core/unet_dataset.py

Defines the PyTorch Global Dataset and custom Loss layers for U-Net spatial forecasting.
"""

import numpy as np
import torch
import torch.nn as nn
from PIL import Image
from scipy.ndimage import distance_transform_edt
from torch.utils.data import Dataset

from core.config import PRECOMPUTED_DIR
from core.utils.image_utils import rgb_to_mask


def compute_distance_transforms(mask: np.ndarray) -> np.ndarray:
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
    return np.stack(dists, axis=-1)  # H x W x 5


class GlobalPatchDataset(Dataset):
    def __init__(
        self,
        zone_keys: list[str],
        year_prev2: int,
        year_prev: int,
        year_target: int | None = None,
        patch_size: int = 128,
        augment: bool = False,
        num_classes: int = 6,
    ):
        self.patch_size = patch_size
        self.augment = augment
        self.num_classes = num_classes
        self.patches = []
        self.zones_data = []

        for zone_key in zone_keys:
            zone_dir = PRECOMPUTED_DIR / zone_key
            if not zone_dir.exists():
                continue

            # Load masks and enforce shape alignment to prevent ValueError shape mismatch
            mask_prev_path = zone_dir / f"mask_rgb_{year_prev}.png"
            if not mask_prev_path.exists():
                mask_prev_path = zone_dir / "mask_rgb_2023.png"
            mask_prev_img = Image.open(mask_prev_path).convert("RGB")
            w, h = mask_prev_img.size
            mask_prev = rgb_to_mask(np.array(mask_prev_img))

            mask_prev2_path = zone_dir / f"mask_rgb_{year_prev2}.png"
            if not mask_prev2_path.exists():
                mask_prev2_path = zone_dir / "mask_rgb_2023.png"
            mask_prev2_img = Image.open(mask_prev2_path).convert("RGB")
            if mask_prev2_img.size != (w, h):
                mask_prev2_img = mask_prev2_img.resize((w, h), Image.Resampling.NEAREST)
            mask_prev2 = rgb_to_mask(np.array(mask_prev2_img))

            mask_target = None
            if year_target is not None:
                mask_target_path = zone_dir / f"mask_rgb_{year_target}.png"
                if not mask_target_path.exists():
                    mask_target_path = zone_dir / "mask_rgb_2023.png"
                mask_target_img = Image.open(mask_target_path).convert("RGB")
                if mask_target_img.size != (w, h):
                    mask_target_img = mask_target_img.resize((w, h), Image.Resampling.NEAREST)
                mask_target = rgb_to_mask(np.array(mask_target_img))

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
                    "w_pad": w + pad_w,
                })

            # Build fixed grid patches
            for py in range(h_patches):
                for px in range(w_patches):
                    y = py * patch_size
                    x = px * patch_size

                    p_mask_prev2 = mask_prev2[y : y + patch_size, x : x + patch_size]
                    p_mask_prev = mask_prev[y : y + patch_size, x : x + patch_size]
                    p_dist_prev2 = dist_prev2[y : y + patch_size, x : x + patch_size]
                    p_dist_prev = dist_prev[y : y + patch_size, x : x + patch_size]
                    p_ndvi_prev2 = ndvi_arr_prev2[y : y + patch_size, x : x + patch_size]
                    p_rgb_prev2 = tc_arr_prev2[y : y + patch_size, x : x + patch_size]
                    p_ndvi_prev = ndvi_arr_prev[y : y + patch_size, x : x + patch_size]
                    p_rgb_prev = tc_arr_prev[y : y + patch_size, x : x + patch_size]

                    p_target = None
                    if mask_target is not None:
                        p_target = mask_target[y : y + patch_size, x : x + patch_size]

                    self.patches.append({
                        "prev2": p_mask_prev2,
                        "prev": p_mask_prev,
                        "dist_prev2": p_dist_prev2,
                        "dist_prev": p_dist_prev,
                        "ndvi_prev2": p_ndvi_prev2,
                        "rgb_prev2": p_rgb_prev2,
                        "ndvi_prev": p_ndvi_prev,
                        "rgb_prev": p_rgb_prev,
                        "target": p_target,
                    })

        if self.augment:
            self.length = len(zone_keys) * 150
            self.h_patches = None
            self.w_patches = None
        else:
            self.h_patches = h_patches
            self.w_patches = w_patches

    def __len__(self) -> int:
        if self.augment:
            return self.length
        return len(self.patches)

    def __getitem__(self, idx: int) -> tuple:
        if self.augment:
            # Dynamic random cropping from a random zone
            zone_idx = idx % len(self.zones_data)
            zone = self.zones_data[zone_idx]
            h_pad, w_pad = zone["h_pad"], zone["w_pad"]

            # Crop coordinates
            y = np.random.randint(0, h_pad - self.patch_size + 1)
            x = np.random.randint(0, w_pad - self.patch_size + 1)

            p_prev2 = zone["mask_prev2"][y : y + self.patch_size, x : x + self.patch_size]
            p_prev = zone["mask_prev"][y : y + self.patch_size, x : x + self.patch_size]
            p_dist_prev2 = zone["dist_prev2"][y : y + self.patch_size, x : x + self.patch_size]
            p_dist_prev = zone["dist_prev"][y : y + self.patch_size, x : x + self.patch_size]
            p_ndvi_prev2 = zone["ndvi_prev2"][y : y + self.patch_size, x : x + self.patch_size]
            p_rgb_prev2 = zone["rgb_prev2"][y : y + self.patch_size, x : x + self.patch_size]
            p_ndvi_prev = zone["ndvi_prev"][y : y + self.patch_size, x : x + self.patch_size]
            p_rgb_prev = zone["rgb_prev"][y : y + self.patch_size, x : x + self.patch_size]

            p_target = None
            if zone["mask_target"] is not None:
                p_target = zone["mask_target"][y : y + self.patch_size, x : x + self.patch_size]

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
        prev2_oh = np.eye(self.num_classes)[p_prev2].transpose(2, 0, 1).astype(np.float32)
        prev_oh = np.eye(self.num_classes)[p_prev].transpose(2, 0, 1).astype(np.float32)
        dist_feat_prev = p_dist_prev.transpose(2, 0, 1)  # 5 x H x W
        # Compute change velocity in distance transforms (spatial change features)
        dist_diff = (p_dist_prev - p_dist_prev2).transpose(2, 0, 1)  # 5 x H x W

        X = np.concatenate([prev2_oh, prev_oh, dist_feat_prev, dist_diff], axis=0)  # 22 channels

        if p_target is not None:
            return (
                torch.tensor(X.copy(), dtype=torch.float32),
                torch.tensor(p_target.copy(), dtype=torch.long),
                torch.tensor(p_prev.copy(), dtype=torch.long),
            )
        return (
            torch.tensor(X.copy(), dtype=torch.float32),
            torch.tensor(p_prev.copy(), dtype=torch.long),
        )


def compute_class_weights(dataset: GlobalPatchDataset, num_classes: int = 6) -> torch.Tensor:
    """Calculate inverse frequency weights for class imbalance."""
    counts = np.zeros(num_classes, dtype=np.int64)
    for p in dataset.patches:
        if p["target"] is not None:
            counts += np.bincount(p["target"].flatten(), minlength=num_classes)
    total = counts.sum()
    if total == 0:
        return torch.ones(num_classes, dtype=torch.float32)
    raw_weights = total / (len(counts) * (counts + 1e-5))
    # Cap weights to avoid rare classes (like class 0) zeroing out others
    capped_weights = np.clip(raw_weights, a_min=0.1, a_max=10.0)
    normalized_weights = capped_weights / capped_weights.sum() * num_classes
    return torch.tensor(normalized_weights, dtype=torch.float32)


class DiceLoss(nn.Module):
    """Multi-class Dice Loss to directly optimize region overlap."""
    def __init__(self, smooth: float = 1.0):
        super().__init__()
        self.smooth = smooth

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
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
    def __init__(self, weight: torch.Tensor | None = None, smooth: float = 1.0):
        super().__init__()
        self.ce = nn.CrossEntropyLoss(weight=weight)
        self.dice = DiceLoss(smooth=smooth)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        return 0.5 * self.ce(logits, targets) + 0.5 * self.dice(logits, targets)


class ChangeWeightedHybridLoss(nn.Module):
    """Dice + Change-Weighted Cross-Entropy Loss."""
    def __init__(self, change_weight: float = 3.0, smooth: float = 1.0):
        super().__init__()
        self.change_weight = change_weight
        self.ce = nn.CrossEntropyLoss(reduction="none")
        self.dice = DiceLoss(smooth=smooth)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor, prev: torch.Tensor) -> torch.Tensor:
        # CE loss (unreduced)
        ce_loss = self.ce(logits, targets)  # (N, H, W)

        # Calculate pixel-wise weights based on whether they transitioned
        change_mask = targets != prev
        weights = torch.ones_like(targets, dtype=torch.float32)
        weights[change_mask] = self.change_weight

        weighted_ce = (ce_loss * weights).mean()
        dice_loss = self.dice(logits, targets)

        return 0.5 * weighted_ce + 0.5 * dice_loss
