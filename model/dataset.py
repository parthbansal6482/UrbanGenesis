"""
model/dataset.py

PyTorch Dataset for SegFormer training on satellite tiles.
Expects tile GeoTIFFs (4-channel) and corresponding label PNGs.
Label classes: 0=background, 1=buildings, 2=roads,
               3=dense_vegetation, 4=water, 5=bare_soil
"""

import numpy as np
import torch
from torch.utils.data import Dataset
import rasterio
from PIL import Image
from pathlib import Path
import albumentations as A
from albumentations.pytorch import ToTensorV2


def get_train_transforms():
    return A.Compose([
        A.RandomRotate90(p=0.5),
        A.HorizontalFlip(p=0.5),
        A.VerticalFlip(p=0.3),
        A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.4),
        A.GaussNoise(var_limit=(10, 50), p=0.3),
        A.CoarseDropout(max_holes=8, max_height=32, max_width=32, p=0.2),
        A.Normalize(
            mean=[0.485, 0.456, 0.406, 0.4],   # R, G, B, NIR means
            std=[0.229, 0.224, 0.225, 0.2],
            max_pixel_value=10000.0,
        ),
        ToTensorV2(),
    ])


def get_val_transforms():
    return A.Compose([
        A.Normalize(
            mean=[0.485, 0.456, 0.406, 0.4],
            std=[0.229, 0.224, 0.225, 0.2],
            max_pixel_value=10000.0,
        ),
        ToTensorV2(),
    ])


class SatelliteSegmentationDataset(Dataset):
    def __init__(self, tile_paths: list, label_paths: list, transforms=None):
        assert len(tile_paths) == len(label_paths), f"Mismatch: {len(tile_paths)} tiles, {len(label_paths)} labels"
        self.tile_paths = tile_paths
        self.label_paths = label_paths
        self.transforms = transforms

    def __len__(self):
        return len(self.tile_paths)

    def __getitem__(self, idx):
        # Load 4-band tile
        with rasterio.open(self.tile_paths[idx]) as src:
            image = src.read().astype(np.float32)   # shape: (4, H, W)
        image = np.transpose(image, (1, 2, 0))       # → (H, W, 4)

        # Load label mask
        label = np.array(Image.open(self.label_paths[idx]))  # shape: (H, W)

        if self.transforms:
            augmented = self.transforms(image=image, mask=label)
            image = augmented["image"]
            label = augmented["mask"]

        return {
            "pixel_values": image,
            "labels": label.long() if isinstance(label, torch.Tensor) else torch.tensor(label, dtype=torch.long),
        }
