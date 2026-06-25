"""
core/bbox_utils.py

Validates and normalizes bounding boxes for arbitrary-region analysis.
Used by both the named-zone path and the new custom-bbox path so that
all inputs go through the same checks before reaching the pipeline.
"""

from typing import Tuple
import math

MAX_BBOX_AREA_DEG2 = 0.25   # ~ roughly 50km x 50km at mid-latitudes — prevents
                             # accidental requests for an entire state/country
MIN_BBOX_AREA_DEG2 = 0.0001  # prevents a degenerate point/sliver request


class InvalidBBoxError(ValueError):
    pass


def validate_bbox(bbox: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """
    bbox: (min_lon, min_lat, max_lon, max_lat)
    Raises InvalidBBoxError with a clear human-readable message if invalid.
    Returns the bbox unchanged if valid.
    """
    if len(bbox) != 4:
        raise InvalidBBoxError("Bounding box must have exactly 4 values: min_lon, min_lat, max_lon, max_lat")

    min_lon, min_lat, max_lon, max_lat = bbox

    if not (-180 <= min_lon <= 180) or not (-180 <= max_lon <= 180):
        raise InvalidBBoxError("Longitude values must be between -180 and 180")
    if not (-90 <= min_lat <= 90) or not (-90 <= max_lat <= 90):
        raise InvalidBBoxError("Latitude values must be between -90 and 90")
    if min_lon >= max_lon:
        raise InvalidBBoxError("min_lon must be less than max_lon")
    if min_lat >= max_lat:
        raise InvalidBBoxError("min_lat must be less than max_lat")

    area = (max_lon - min_lon) * (max_lat - min_lat)
    if area > MAX_BBOX_AREA_DEG2:
        raise InvalidBBoxError(
            f"Bounding box too large ({area:.3f} deg²). "
            f"Maximum supported area is {MAX_BBOX_AREA_DEG2} deg² (~50km x 50km). "
            f"Please select a smaller region."
        )
    if area < MIN_BBOX_AREA_DEG2:
        raise InvalidBBoxError("Bounding box too small. Please select a wider region.")

    return (min_lon, min_lat, max_lon, max_lat)


def bbox_cache_key(bbox: Tuple[float, float, float, float], precision: int = 3) -> str:
    """
    Generates a normalized cache key for a bbox by snapping coordinates
    to a fixed grid. This means two slightly different but overlapping
    bbox requests (e.g. from imprecise map-drawing) resolve to the
    same cached result instead of triggering a duplicate fetch.

    precision=3 means snapping to ~0.001 degree (~111m) grid cells.
    """
    snapped = tuple(round(coord, precision) for coord in bbox)
    return f"bbox_{snapped[0]}_{snapped[1]}_{snapped[2]}_{snapped[3]}"
