"""
api/dependencies.py

Shared FastAPI dependencies and service-layer helpers.

- load_zone_verdict()   LRU-cached loader for precomputed verdict.json files.
                        Sanitizes NaN/Infinity so they never reach JSON responses.
- get_zones_config()    Returns the authoritative zone configuration dict.
"""

import functools
import json
import logging
from typing import Optional

from core.config import PRECOMPUTED_DIR, ZONES_CONFIG, safe_float

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=16)
def load_zone_verdict(zone_key: str) -> Optional[dict]:
    """
    Load and sanitize the precomputed verdict.json for a zone.

    Results are cached in-process after the first read.  The cache is
    keyed by *zone_key*; restarting the server clears it.

    Args:
        zone_key: A key from ZONES_CONFIG (whitelist-validated by callers).

    Returns:
        Sanitized verdict dict, or None if the file does not exist or
        cannot be parsed.
    """
    # Prevent directory traversal — only allow whitelisted zone keys
    if zone_key not in ZONES_CONFIG:
        logger.warning("Unauthorized or invalid zone_key: %s", zone_key)
        return None

    verdict_path = PRECOMPUTED_DIR / zone_key / "verdict.json"
    if not verdict_path.exists():
        return None

    try:
        raw = verdict_path.read_text()
        # Neutralize JSON-invalid tokens that Python's json.dumps may emit
        raw = raw.replace(": Infinity", ": 99.99").replace(":Infinity", ":99.99")
        raw = raw.replace(": NaN", ": null").replace(":NaN", ":null")
        data = json.loads(raw)

        # Sanitise top-level numeric fields
        data["abi"] = safe_float(data.get("abi"), 0.0)
        data["overall_abi_change_pct"] = safe_float(data.get("overall_abi_change_pct"), 0.0)
        data["cropland_loss_ha"] = safe_float(data.get("cropland_loss_ha"), 0.0)

        # Sanitise per-year timeseries records
        for rec in data.get("timeseries", []):
            rec["abi"] = safe_float(rec.get("abi"), 0.0)
            rec["cropland_pixels"] = int(rec.get("cropland_pixels", 0))
            rec["vegetation_pixels"] = int(rec.get("vegetation_pixels", 0))
            rec["water_pixels"] = int(rec.get("water_pixels", 0))
            rec["buildings_pixels"] = int(rec.get("buildings_pixels", 0))
            rec["soil_pixels"] = int(rec.get("soil_pixels", 0))
            rec["cropland_pct"] = safe_float(rec.get("cropland_pct"), 0.0)
            rec["vegetation_pct"] = safe_float(rec.get("vegetation_pct"), 0.0)
            rec["water_pct"] = safe_float(rec.get("water_pct"), 0.0)
            rec["buildings_pct"] = safe_float(rec.get("buildings_pct"), 0.0)
            rec["soil_pct"] = safe_float(rec.get("soil_pct"), 0.0)

        return data

    except Exception as exc:
        logger.error("Error loading verdict.json for zone %s: %s", zone_key, exc)
        return None


def get_zones_config() -> dict:
    """Return the authoritative zone configuration dict."""
    return ZONES_CONFIG
