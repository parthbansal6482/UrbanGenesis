"""
analytics/change_detection.py

Computes transition matrices and detects key spatial changes between
multi-temporal land use masks. Updated for FarmGuard 7-class map:
  0=background, 1=buildings, 2=roads, 3=cropland,
  4=dense_vegetation, 5=water, 6=bare_soil
"""

import numpy as np
from typing import Dict


def compute_transition_matrix(
    mask_before: np.ndarray,
    mask_after: np.ndarray,
    num_classes: int = 6,
) -> np.ndarray:
    """
    Compute transition matrix where entry (i, j) is the number of pixels
    that changed from class i to class j.

    Args:
        mask_before: np.ndarray (H, W) — earlier year mask
        mask_after:  np.ndarray (H, W) — later year mask
        num_classes: total number of classes (default: 6 for FarmGuard)

    Returns:
        np.ndarray of shape (num_classes, num_classes), dtype int64
    """
    assert mask_before.shape == mask_after.shape, (
        f"Mask shapes must match: {mask_before.shape} vs {mask_after.shape}"
    )

    flat_before = mask_before.flatten()
    flat_after = mask_after.flatten()

    matrix, _, _ = np.histogram2d(
        flat_before, flat_after,
        bins=(num_classes, num_classes),
        range=((0, num_classes), (0, num_classes))
    )
    return matrix.astype(np.int64)


def detect_urban_expansion(
    mask_before: np.ndarray,
    mask_after: np.ndarray,
) -> Dict[str, float]:
    """
    Detects key indicators of urban expansion into agricultural buffer:
    - Buffer (cropland + vegetation + water) loss to encroachment (buildings)
    - Net growth in built-up area

    Args:
        mask_before: np.ndarray (H, W) — earlier year mask
        mask_after:  np.ndarray (H, W) — later year mask

    Returns:
        dict with buffer_to_encroachment_loss_pixels, buffer_to_encroachment_loss_pct,
        infrastructure_net_increase_pixels, infrastructure_growth_pct
    """
    transition = compute_transition_matrix(mask_before, mask_after)

    # Buffer classes: 2=cropland, 3=dense_vegetation, 4=water
    # Encroachment classes: 1=buildings
    buffer_indices = [2, 3, 4]
    encroach_indices = [1]

    total_pixels = mask_before.size
    buffer_to_encroach_pixels = 0
    for b in buffer_indices:
        for e in encroach_indices:
            buffer_to_encroach_pixels += transition[b, e]

    before_infra = np.isin(mask_before, encroach_indices).sum()
    after_infra = np.isin(mask_after, encroach_indices).sum()
    infra_increase = after_infra - before_infra

    return {
        "buffer_to_encroachment_loss_pixels": int(buffer_to_encroach_pixels),
        "buffer_to_encroachment_loss_pct": round(
            float(buffer_to_encroach_pixels / total_pixels * 100), 2
        ),
        "infrastructure_net_increase_pixels": int(infra_increase),
        "infrastructure_growth_pct": round(
            float(infra_increase / max(1, before_infra) * 100), 2
        ),
    }

