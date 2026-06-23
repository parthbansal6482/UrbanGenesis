"""
core/class_map.py

Single source of truth for all land-cover class definitions used
across the FarmGuard platform.

Eliminates duplication between app.py, fetch_esri_landcover.py, and
the analytics layer by providing one canonical import path.

Classes (FarmGuard 6-class schema):
    0 — Background / nodata
    1 — Buildings (urban infrastructure / encroachment)
    2 — Cropland  (agricultural buffer — KEY class)
    3 — Dense Vegetation (forest / tree cover)
    4 — Water Bodies (reservoirs / rivers)
    5 — Bare Soil (fallow / barren land)

ESRI Annual Land Cover (io-lulc-annual-v02) remapping:
    ESRI classes are remapped to the FarmGuard schema before any
    analytics or visualization takes place.
"""

import numpy as np

# ---------------------------------------------------------------------------
# FarmGuard class registry
# ---------------------------------------------------------------------------

CLASS_INFO: dict[int, dict] = {
    0: {"name": "Background",        "color": "#000000", "emoji": "⬛"},
    1: {"name": "Buildings",          "color": "#DC2626", "emoji": "🏢"},
    2: {"name": "Cropland",           "color": "#D4A017", "emoji": "🌾"},
    3: {"name": "Dense Vegetation",   "color": "#228B22", "emoji": "🌳"},
    4: {"name": "Water Bodies",       "color": "#1E64C8", "emoji": "💧"},
    5: {"name": "Bare Soil",          "color": "#D2B48C", "emoji": "🏜️"},
}

# Tuple-form palette — used by pipeline image generation functions
CLASS_COLORS: dict[int, tuple[int, int, int]] = {
    0: (0,   0,   0),    # background  — black
    1: (220, 38,  38),   # buildings   — red
    2: (212, 160, 23),   # cropland    — gold
    3: (34,  139, 34),   # dense veg   — green
    4: (30,  100, 200),  # water       — blue
    5: (210, 180, 140),  # bare soil   — tan
}

# Pre-computed numpy uint8 arrays of each class color — used by image_utils
# for vectorized mask ↔ RGB conversion (avoids repeated hex parsing at request time)
CLASS_RGB: dict[int, np.ndarray] = {
    cls_id: np.array(
        [int(info["color"].lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)],
        dtype=np.uint8,
    )
    for cls_id, info in CLASS_INFO.items()
}

# ---------------------------------------------------------------------------
# ESRI Annual Land Cover → FarmGuard class remapping
# Source: io-lulc-annual-v02 (Microsoft Planetary Computer)
# ---------------------------------------------------------------------------

ESRI_TO_FARMGUARD: dict[int, int] = {
    0:  0,  # nodata        → background
    1:  4,  # water         → water
    2:  3,  # trees         → dense_vegetation
    3:  3,  # grass         → dense_vegetation
    4:  3,  # flooded_veg   → dense_vegetation
    5:  2,  # crops         → cropland  ← THE KEY CLASS
    6:  5,  # scrub/shrub   → bare_soil
    7:  1,  # built area    → buildings
    8:  5,  # bare ground   → bare_soil
    9:  0,  # snow/ice      → background
    10: 0,  # clouds        → background
    11: 5,  # rangeland     → bare_soil
}
