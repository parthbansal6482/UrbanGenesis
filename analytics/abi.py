"""
analytics/abi.py

Computes the Agricultural Buffer Index (ABI) — a measure of how much
agricultural and natural land remains as a buffer against urban encroachment.

Designed for Satyukt Analytics use cases:
  - Sat4Risk: ABI drop → elevated flood and drought risk for adjacent farms
  - MRV Carbon Credit: multi-year ABI timeseries = verifiable vegetation baseline
  - Crop Insurance: ABI grade → risk tier for premium recalculation

Class map (must match model/dataset.py):
  0 = background
  1 = buildings
  2 = roads
  3 = cropland          ← KEY ADDITION vs previous version
  4 = dense_vegetation
  5 = water
  6 = bare_soil

ABI = (cropland + dense_vegetation + water) / (buildings + roads)

Interpretation:
  ABI > 2.0  → Healthy buffer. Farmland well-protected.
  ABI 1–2    → Moderate. Monitor annually.
  ABI 0.5–1  → Elevated. Urban boundary encroaching.
  ABI 0.3–0.5→ High risk. Active cropland conversion detected.
  ABI < 0.3  → Critical. Immediate MRV review and insurance flag.
"""

import numpy as np
from pathlib import Path
from PIL import Image
from typing import Dict, List

# Classes that form the agricultural/natural buffer
BUFFER_CLASSES = {2, 3, 4}       # cropland, dense_vegetation, water
ENCROACH_CLASSES = {1}           # buildings (encroachment)
CROPLAND_CLASS = 2


def compute_abi(mask: np.ndarray) -> Dict:
    """
    Compute ABI and component pixel counts from a segmentation mask.

    Args:
        mask: np.ndarray shape (H, W), integer values 0–5

    Returns:
        dict with keys: abi, cropland_pixels, vegetation_pixels, water_pixels,
        buildings_pixels, buffer_pixels, encroach_pixels,
        cropland_pct, encroach_pct
    """
    total = mask.size

    cropland_px = int((mask == CROPLAND_CLASS).sum())
    vegetation_px = int((mask == 3).sum())
    water_px = int((mask == 4).sum())
    buildings_px = int((mask == 1).sum())

    buffer_px = cropland_px + vegetation_px + water_px
    encroach_px = buildings_px

    abi = float(buffer_px) / encroach_px if encroach_px > 0 else float("inf")

    return {
        "abi": round(abi, 4),
        "cropland_pixels": cropland_px,
        "vegetation_pixels": vegetation_px,
        "water_pixels": water_px,
        "buildings_pixels": buildings_px,
        "buffer_pixels": buffer_px,
        "encroach_pixels": encroach_px,
        "cropland_pct": round(cropland_px / total * 100, 2),
        "encroach_pct": round(encroach_px / total * 100, 2),
    }


def compute_abi_from_file(mask_path: Path) -> Dict:
    """Load a mask PNG and compute ABI from it."""
    mask = np.array(Image.open(mask_path))
    return compute_abi(mask)


def compute_abi_timeseries(mask_paths_by_year: Dict[int, Path]) -> List[Dict]:
    """
    Compute ABI for each year and return ordered list of yearly records.

    Args:
        mask_paths_by_year: {2018: Path(...), 2020: Path(...), 2022: Path(...)}

    Returns:
        List of dicts, one per year, each containing ABI metrics and a 'year' key.
    """
    records = []
    for year in sorted(mask_paths_by_year.keys()):
        result = compute_abi_from_file(mask_paths_by_year[year])
        result["year"] = year
        records.append(result)
    return records


def compute_cropland_loss_ha(
    mask_before: np.ndarray,
    mask_after: np.ndarray,
    resolution_m: float = 10.0,
) -> float:
    """
    Compute hectares of cropland lost between two segmentation masks.

    Args:
        mask_before: np.ndarray (H, W) — earlier year mask
        mask_after:  np.ndarray (H, W) — later year mask
        resolution_m: pixel size in METRES (not km, not degrees).
                      Sentinel-2 native = 10.0 m.
                      Landsat-8 = 30.0 m.
                      Must satisfy 0.5 <= resolution_m <= 100.

    Returns:
        float — hectares of cropland lost (0.0 if none lost)

    Raises:
        AssertionError: if resolution_m is outside the valid metre range.
    """
    assert 0.5 <= resolution_m <= 100, (
        f"resolution_m={resolution_m} is out of range [0.5, 100]. "
        "Value must be in metres (e.g. 10.0 for Sentinel-2, 30.0 for Landsat)."
    )
    cropland_before = (mask_before == CROPLAND_CLASS).sum()
    cropland_after = (mask_after == CROPLAND_CLASS).sum()
    lost_pixels = max(0, int(cropland_before) - int(cropland_after))
    lost_m2 = lost_pixels * (resolution_m ** 2)
    lost_ha = lost_m2 / 10_000
    return round(float(lost_ha), 2)
