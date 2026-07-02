"""
core/config.py

Project-wide configuration loading and path resolution.

Reads config/settings.yaml once and exposes resolved Path constants
and the raw config dict. Also provides the safe_float() sanitizer
used throughout the API layer to prevent NaN/Infinity from leaking
into JSON responses.
"""

import logging
import math
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical project paths
# ---------------------------------------------------------------------------

BASE_DIR: Path = Path(__file__).resolve().parent.parent
CONFIG_PATH: Path = BASE_DIR / "config" / "settings.yaml"
PRECOMPUTED_DIR: Path = BASE_DIR / "demo" / "precomputed"

# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------

_DEFAULT_ZONES: dict[str, Any] = {
    "nashik_north": {
        "name": "Nashik North Agricultural Zone",
        "bbox": [73.72, 20.05, 73.98, 20.25],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Grape and onion belt. Sat4Risk flood zone. MRV baseline.",
    },
    "vijayawada_west": {
        "name": "Vijayawada West Farmland",
        "bbox": [80.45, 16.45, 80.70, 16.65],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Krishna delta cropland. Insurance client region.",
    },
    "hubli_outskirts": {
        "name": "Hubli Peripheral Agricultural Zone",
        "bbox": [74.95, 15.28, 75.20, 15.48],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Karnataka agri zone. Satyukt active partner region.",
    },
    "bengaluru": {
        "name": "Bengaluru Agricultural Buffer Zone",
        "bbox": [77.45, 12.83, 77.75, 13.10],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Satyukt headquarters regional cropland buffer tracker.",
    },
    "pune_east": {
        "name": "Pune East Tech-Cropland Zone",
        "bbox": [73.95, 18.45, 74.20, 18.65],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Sugarcane and vegetable farms next to high-growth IT hubs.",
    },
    "jaipur_south": {
        "name": "Jaipur South Arid Agricultural Zone",
        "bbox": [75.75, 26.70, 76.00, 26.90],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Arid crops and shifting soils under heritage/industrial expansion.",
    },
    "ludhiana_rural": {
        "name": "Ludhiana Rural Industrial Cropland",
        "bbox": [75.70, 30.80, 75.95, 31.00],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "High-intensity wheat/paddy crop belt surrounding industrial sprawl.",
    },
    "coimbatore_north": {
        "name": "Coimbatore North Coconut-Crop Belt",
        "bbox": [76.90, 11.05, 77.15, 11.25],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Coconut plantations and cash crops facing manufacturing growth.",
    },
    "patna_west": {
        "name": "Patna West Gangetic Alluvial Farmland",
        "bbox": [84.95, 25.55, 85.20, 25.75],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Highly fertile Gangetic alluvial crop boundary.",
    },
    "indore_peripheral": {
        "name": "Indore Peripheral Soybean Belt",
        "bbox": [75.80, 22.60, 76.05, 22.80],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Black soil soybean and wheat farming tracts under urban pressure.",
    },
    "guwahati_east": {
        "name": "Guwahati East Riverine Crop Zone",
        "bbox": [91.80, 26.10, 92.05, 26.30],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Wetland and riverine crop regions in the Brahmaputra valley.",
    },
    "hyderabad_west": {
        "name": "Hyderabad West Semi-Arid Farms",
        "bbox": [78.15, 17.35, 78.40, 17.55],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Dryland crop boundary facing aggressive IT corridor sprawl.",
    },
    "lucknow_outer": {
        "name": "Lucknow Outer Orchard-Crop Belt",
        "bbox": [80.85, 26.75, 81.10, 26.95],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Traditional mango orchards and crop fields undergoing expansion.",
    },
    "nagpur_rural": {
        "name": "Nagpur Rural Citrus-Cotton Belt",
        "bbox": [78.95, 21.05, 79.20, 21.25],
        "years": [2017, 2019, 2021, 2023, 2025],
        "satyukt_relevance": "Central Indian cotton and orange grove agricultural buffer.",
    },
}


def load_config() -> dict[str, Any]:
    """
    Load and return the full settings.yaml configuration dict.

    Falls back to a minimal hard-coded config if the file cannot be
    read, so the API still starts in degraded mode.
    """
    try:
        with open(CONFIG_PATH) as fh:
            return yaml.safe_load(fh)
    except Exception as exc:
        logger.error("Failed to load config/settings.yaml: %s", exc)
        return {"zones": _DEFAULT_ZONES}


# Module-level singleton — loaded once at import time
_config: dict[str, Any] = load_config()

ZONES_CONFIG: dict[str, Any] = _config.get("zones", _DEFAULT_ZONES)

# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Coerce *value* to a finite float, replacing NaN and ±Inf.

    Args:
        value:   Input value (any type accepted by float()).
        default: Returned when *value* is NaN, -Inf, or not convertible.

    Returns:
        A finite float; +Inf is capped at 99.99.
    """
    try:
        f = float(value)
        if math.isnan(f):
            return default
        if math.isinf(f):
            return 99.99 if f > 0 else default
        return f
    except (TypeError, ValueError):
        return default
