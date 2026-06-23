"""
pipeline/mock_generator.py

Spatially-coherent synthetic land-cover data for offline development
and CI pipelines (no Planetary Computer credentials required).

The mock uses Gaussian-blurred noise with rank-based pixel assignment
to produce realistic field/neighbourhood spatial patterns. Zone-specific
class proportions follow historically-accurate trajectories.

Functions:
    generate_realistic_mock()  — uint8 FarmGuard class-ID mask
    mask_to_true_color()       — synthetic satellite true-color image
    mask_to_ndvi()             — synthetic NDVI colorized visualization
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Zone-specific land-cover class proportion profiles
# ---------------------------------------------------------------------------
# Proportions are expressed as fractions of total pixels.
# t_pct = normalized time position (0 at 2018, 1 at 2024).
# Classes: cropland, buildings, vegetation, water, bare_soil

_ZONE_PROFILES: dict[str, dict[str, float]] = {
    "nashik_north": {
        "cropland": 0.50,
        "buildings": 0.08,
        "vegetation": 0.14,
        "water": 0.04,
        "bare_soil": 0.21,
        # annual drift rates
        "_cropland_drift": -0.18,
        "_buildings_drift": +0.14,
    },
    "vijayawada_west": {
        "cropland": 0.62,
        "buildings": 0.05,
        "vegetation": 0.08,
        "water": 0.15,
        "bare_soil": 0.08,
        "_cropland_drift": -0.10,
        "_buildings_drift": +0.08,
    },
    "hubli_outskirts": {
        "cropland": 0.55,
        "buildings": 0.06,
        "vegetation": 0.10,
        "water": 0.03,
        "bare_soil": 0.23,
        "_cropland_drift": -0.20,
        "_buildings_drift": +0.18,
    },
    "bengaluru": {
        "cropland": 0.10,
        "buildings": 0.45,
        "vegetation": 0.25,
        "water": 0.02,
        "bare_soil": 0.14,
        "_cropland_drift": -0.06,
        "_buildings_drift": +0.15,
    },
}


def _resolve_profile(zone_key: str, t_pct: float) -> dict[str, float]:
    """Compute the class proportions for a zone at normalized time *t_pct*."""
    base = _ZONE_PROFILES.get(zone_key, _ZONE_PROFILES["nashik_north"])
    profile = {
        "cropland":   max(0.01, base["cropland"]  + base.get("_cropland_drift",  0.0) * t_pct),
        "buildings":  min(0.80, base["buildings"] + base.get("_buildings_drift", 0.0) * t_pct),
        "vegetation": base["vegetation"],
        "water":      base["water"],
        "bare_soil":  max(0.01, base["bare_soil"]),
    }
    # Normalize so fractions sum to 1
    total = sum(profile.values())
    return {k: max(0.0, v / total) for k, v in profile.items()}


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def generate_realistic_mock(zone_key: str, year: int, size: int = 1024) -> np.ndarray:
    """
    Generate a spatially-coherent synthetic FarmGuard land-cover mask.

    Uses Gaussian-blurred uniform noise with rank-based pixel assignment
    to guarantee exact class proportions while producing realistic spatial
    clustering (field patterns, neighbourhood blocks).

    Args:
        zone_key: Zone identifier (e.g. "nashik_north").
        year:     Target year — drives class proportion interpolation.
        size:     Output spatial dimension in pixels (square).

    Returns:
        np.ndarray of shape (size, size), dtype uint8 — FarmGuard class IDs.
    """
    from scipy.ndimage import gaussian_filter

    rng = np.random.default_rng(hash(zone_key) % (2**32) + year)
    t_pct = (year - 2018) / max((2024 - 2018), 1)

    profile = _resolve_profile(zone_key, t_pct)

    # Large-scale spatial coherence: blurred noise → rank-based assignment
    noise = rng.random((size, size)).astype(np.float32)
    noise_blurred = gaussian_filter(noise, sigma=30)
    sorted_indices = np.argsort(noise_blurred.flatten())
    total_pixels = size * size

    mask_flat = np.zeros(total_pixels, dtype=np.uint8)
    start_idx = 0
    for cls_id, key in [
        (1, "buildings"),
        (2, "cropland"),
        (3, "vegetation"),
        (4, "water"),
        (5, "bare_soil"),
    ]:
        frac = profile.get(key, 0.0)
        n_pixels = int(round(frac * total_pixels))
        end_idx = min(start_idx + n_pixels, total_pixels)
        mask_flat[sorted_indices[start_idx:end_idx]] = cls_id
        start_idx = end_idx

    # Fill any remainder with bare soil
    if start_idx < total_pixels:
        mask_flat[sorted_indices[start_idx:]] = 5

    mask = mask_flat.reshape((size, size))

    # Fine-scale road network overlay
    fine_noise = rng.random((size, size)).astype(np.float32)
    fine_blurred = gaussian_filter(fine_noise, sigma=6)
    fine_blurred = (fine_blurred - fine_blurred.min()) / (fine_blurred.max() - fine_blurred.min() + 1e-8)
    road_mask = fine_blurred > 0.93
    mask[road_mask & (mask != 4) & (mask != 1)] = 5   # roads as bare soil

    return mask


def mask_to_true_color(mask: np.ndarray, size: int, year: int) -> np.ndarray:
    """
    Generate a synthetic satellite true-color image from a land-cover mask.

    Each class receives a realistic approximate RGB value with small
    per-pixel noise added for visual realism.

    Args:
        mask: uint8 class-ID mask of shape (size, size).
        size: Spatial dimension in pixels.
        year: Random seed influence (different years produce slightly different noise).

    Returns:
        np.ndarray of shape (size, size, 3), dtype uint8.
    """
    rng = np.random.default_rng(year)
    tc = np.zeros((size, size, 3), dtype=np.uint8)

    class_rgb = {
        0: (30,  30,  35),    # background
        1: (195, 195, 200),   # buildings
        2: (85,  85,  90),    # roads (bare soil variant)
        3: (160, 185, 80),    # cropland
        4: (45,  110, 50),    # dense vegetation
        5: (40,  80,  160),   # water
    }

    for cls_id, rgb in class_rgb.items():
        px = mask == cls_id
        if px.any():
            tc[px] = rgb

    noise = rng.integers(-18, 18, (size, size, 3), dtype=np.int16)
    return np.clip(tc.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def mask_to_ndvi(mask: np.ndarray, size: int, year: int) -> np.ndarray:
    """
    Generate a synthetic NDVI colorized visualization from a land-cover mask.

    Approximates per-class NDVI values and adds realistic noise, then
    applies the RdYlGn colormap.

    Args:
        mask: uint8 class-ID mask of shape (size, size).
        size: Spatial dimension in pixels.
        year: Random seed influence.

    Returns:
        np.ndarray of shape (size, size, 3), dtype uint8 — RGB NDVI map.
    """
    import matplotlib
    import matplotlib.cm as cm  # noqa: F401

    rng = np.random.default_rng(year + 1000)
    ndvi = np.zeros((size, size), dtype=np.float32)

    class_ndvi = {0: -0.1, 1: 0.02, 2: 0.01, 3: 0.45, 4: 0.72, 5: -0.12}
    for cls_id, val in class_ndvi.items():
        ndvi[mask == cls_id] = val

    ndvi += rng.normal(0, 0.04, (size, size)).astype(np.float32)
    ndvi_clipped = np.clip(ndvi, -0.1, 0.8)
    norm = (ndvi_clipped - (-0.1)) / 0.9

    cmap = matplotlib.colormaps["RdYlGn"]
    rgba = (cmap(norm) * 255).astype(np.uint8)
    return rgba[:, :, :3]
