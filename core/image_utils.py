"""
core/image_utils.py

Low-level image conversion utilities shared between the API layer
(dynamic heatmap generation) and the pipeline (precomputed asset
generation).

All functions operate on numpy arrays and have no dependency on
FastAPI, the analytics layer, or the pipeline.
"""

import numpy as np
from core.class_map import CLASS_COLORS, CLASS_RGB


def mask_to_rgb(mask: np.ndarray) -> np.ndarray:
    """
    Convert an integer class-ID mask to an RGB visualization.

    Args:
        mask: np.ndarray of shape (H, W), dtype uint8.
              Each pixel value is a FarmGuard class ID (0–5).

    Returns:
        np.ndarray of shape (H, W, 3), dtype uint8 — an RGB image
        using the canonical FarmGuard color palette.
    """
    h, w = mask.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    for cls_id, color in CLASS_COLORS.items():
        rgb[mask == cls_id] = color
    return rgb


def rgb_to_mask(rgb_img: np.ndarray) -> np.ndarray:
    """
    Convert an RGB segmentation visualization back into a class-ID mask.

    Uses pre-computed uint8 color arrays for fully vectorized matching
    — no per-pixel loops.

    Args:
        rgb_img: np.ndarray of shape (H, W, 3), dtype uint8.
                 Must be an image rendered with the canonical FarmGuard
                 color palette (see core/class_map.py).

    Returns:
        np.ndarray of shape (H, W), dtype uint8 — class-ID mask.
        Pixels that do not match any known class default to 0
        (background).
    """
    h, w = rgb_img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for cls_id, rgb_color in CLASS_RGB.items():
        match = np.all(rgb_img == rgb_color, axis=-1)
        mask[match] = cls_id
    return mask
