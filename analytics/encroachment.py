"""
analytics/encroachment.py

Calculates the spatial encroachment of infrastructure (buildings and roads) on cropland,
vegation, bare soil, and water bodies. Converts pixel measurements to hectares.
Heatmap layers: existing_infra (slate), new_infra on veg/soil (orange), cropland_lost (red), water_lost (cyan).
Supports both SegFormer and ESRI landcover class mappings.
"""

import numpy as np
from typing import Dict, Tuple

# Pixel resolution area in hectares: Sentinel-2 resolution is 10m x 10m = 100 sq meters.
# 1 hectare = 10,000 sq meters. So 1 pixel = 100 / 10000 = 0.01 hectares.
PIXEL_TO_HECTARES = 0.01

def get_class_sets(mapping_type: str = "esri") -> Tuple[set, set, set]:
    """
    Returns (cropland_nature_classes, water_classes, infra_classes) based on mapping type.
    """
    if mapping_type == "segformer":
        # 0: background, 1: buildings, 2: roads, 3: dense_veg, 4: water, 5: bare_soil
        cropland_nature = {3, 5}
        water = {4}
        infra = {1, 2}
    else:
        # esri: 0: bg, 1: buildings, 2: cropland, 3: dense_veg, 4: water, 5: bare_soil
        cropland_nature = {2, 3, 5}
        water = {4}
        infra = {1}
    return cropland_nature, water, infra

def calculate_encroachment_stats(mask_before: np.ndarray, mask_after: np.ndarray, mapping_type: str = "esri") -> Dict[str, float]:
    """
    Compares two land-cover masks (earliest vs latest) and calculates
    encroachment metrics in hectares.
    """
    assert mask_before.shape == mask_after.shape, "Mask shapes must match."
    
    cropland_nature, water, infra = get_class_sets(mapping_type)

    # Identify masks
    is_cropland_before = np.isin(mask_before, list(cropland_nature))
    is_water_before = np.isin(mask_before, list(water))
    
    is_infra_after = np.isin(mask_after, list(infra))

    # Calculate pixel counts for encroachment
    cropland_lost_px = np.logical_and(is_cropland_before, is_infra_after).sum()
    water_lost_px = np.logical_and(is_water_before, is_infra_after).sum()

    return {
        "total_cropland_lost_ha": round(float(cropland_lost_px * PIXEL_TO_HECTARES), 2),
        "total_water_lost_ha": round(float(water_lost_px * PIXEL_TO_HECTARES), 2),
    }

def generate_encroachment_heatmap(mask_before: np.ndarray, mask_after: np.ndarray, mapping_type: str = "esri") -> np.ndarray:
    """
    Generates an RGB visualization showing where encroachment has occurred.

    Layer rendering order (back to front):
      - Unchanged nature / background:               Dark blue-grey  (15, 23, 42)
      - Unchanged / existing infrastructure:         Slate grey      (71, 85, 105)
      - NEW infrastructure on bare soil / veg:       Orange-yellow   (234, 179, 8)   [NEWLY ADDED]
      - Cropland lost to buildings / roads:          Bright red      (239, 68, 68)
      - Water bodies lost to buildings / roads:      Electric cyan   (6, 182, 212)
    """
    assert mask_before.shape == mask_after.shape, "Mask shapes must match."

    cropland_nature, water, infra = get_class_sets(mapping_type)

    h, w = mask_before.shape
    heatmap = np.zeros((h, w, 3), dtype=np.uint8)

    # Base background
    heatmap[:, :] = [15, 23, 42]  # Dark background

    # Pre-compute boolean masks for before/after states
    is_cropland_before = np.isin(mask_before, list(cropland_nature))
    is_water_before    = np.isin(mask_before, list(water))
    is_infra_before    = np.isin(mask_before, list(infra))

    is_infra_after     = np.isin(mask_after, list(infra))

    # Transition layers (applied back-to-front so high-priority overwrites low-priority)
    existing_infra = np.logical_and(is_infra_before, is_infra_after)
    new_infra      = np.logical_and(~is_infra_before, is_infra_after)  # new this period
    new_infra_not_crop_water = np.logical_and(new_infra, ~is_cropland_before)
    new_infra_not_crop_water = np.logical_and(new_infra_not_crop_water, ~is_water_before)
    cropland_lost  = np.logical_and(is_cropland_before, is_infra_after)
    water_lost     = np.logical_and(is_water_before, is_infra_after)

    # Back-to-front paint
    heatmap[existing_infra]           = [71, 85, 105]   # Slate grey
    heatmap[new_infra_not_crop_water] = [234, 179, 8]   # Orange-yellow (new infra on veg/soil)
    heatmap[cropland_lost]            = [239, 68, 68]   # Bright red
    heatmap[water_lost]               = [6, 182, 212]   # Electric cyan

    return heatmap
