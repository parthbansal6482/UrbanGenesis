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
