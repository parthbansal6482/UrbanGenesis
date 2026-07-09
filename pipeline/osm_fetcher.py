"""
pipeline/osm_fetcher.py

Fetches road geometry from OpenStreetMap (Overpass API) for a given bounding box,
caches it to disk, rasterizes the lines, and computes a proximity grid using EDT.
"""

import json
import logging
import urllib.parse
import urllib.request
from pathlib import Path
import numpy as np
from scipy.ndimage import distance_transform_edt

from core.config import PRECOMPUTED_DIR

logger = logging.getLogger(__name__)


def bresenham_line(x0: int, y0: int, x1: int, y1: int, shape: tuple[int, int]) -> list[tuple[int, int]]:
    """Generate pixel coordinates along a line segment using Bresenham's algorithm."""
    h, w = shape
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        if 0 <= y0 < h and 0 <= x0 < w:
            points.append((y0, x0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy

    return points


def fetch_osm_roads(bbox: list[float]) -> list[list[list[float]]]:
    """
    Fetch motorway, primary, secondary, and tertiary highways from Overpass API.
    Returns a list of linestrings, where each linestring is a list of [lon, lat] points.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    
    # Overpass QL query targeting major highways with geometry returned
    query = f"""
    [out:json][timeout:15];
    (
      way["highway"~"motorway|trunk|primary|secondary|tertiary"]({lat_min},{lon_min},{lat_max},{lon_max});
    );
    out geom;
    """
    
    url = "https://overpass-api.de/api/interpreter"
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "FarmGuardSurveillance/1.0"})
    
    logger.info("Querying OpenStreetMap Overpass API for major roads...")
    with urllib.request.urlopen(req, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"Overpass API returned status code {response.status}")
        result = json.loads(response.read().decode("utf-8"))
        
    linestrings = []
    for element in result.get("elements", []):
        if element.get("type") == "way" and "geometry" in element:
            coords = [[pt["lon"], pt["lat"]] for pt in element["geometry"]]
            if coords:
                linestrings.append(coords)
                
    return linestrings


def get_road_proximity_grid(zone_key: str, bbox: list[float], shape: tuple[int, int]) -> np.ndarray:
    """
    Get the Euclidean distance transform grid of the road network.
    Uses local cache if available, otherwise queries OSM with a synthetic fallback.
    """
    h, w = shape
    cache_dir = PRECOMPUTED_DIR / zone_key
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "osm_roads.json"
    
    roads = None
    if cache_path.exists():
        try:
            with open(cache_path) as f:
                roads = json.load(f)
            logger.info("Loaded road network from cache: %s", cache_path)
        except Exception as exc:
            logger.warning("Failed to load cached road file: %s — refetching.", exc)
            
    if roads is None:
        try:
            roads = fetch_osm_roads(bbox)
            with open(cache_path, "w") as f:
                json.dump(roads, f)
            logger.info("Saved OSM road network to cache: %s", cache_path)
        except Exception as exc:
            logger.error("OSM road fetch failed: %s — generating synthetic diagonal road fallback.", exc)
            # Create a simple diagonal highway running from bottom-left to top-right
            lon_min, lat_min, lon_max, lat_max = bbox
            roads = [
                [[lon_min, lat_min], [lon_max, lat_max]]
            ]
            
    # Rasterize roads onto a binary mask
    road_mask = np.zeros((h, w), dtype=np.uint8)
    lon_min, lat_min, lon_max, lat_max = bbox
    lon_range = lon_max - lon_min if lon_max != lon_min else 1e-5
    lat_range = lat_max - lat_min if lat_max != lat_min else 1e-5
    
    for road in roads:
        # Convert road nodes to pixel coordinates
        pixels = []
        for lon, lat in road:
            # Map lon to x [0, w-1]
            x = int(round(((lon - lon_min) / lon_range) * (w - 1)))
            # Map lat to y [h-1, 0] (y=0 is top, lat_max is top)
            y = int(round(((lat_max - lat) / lat_range) * (h - 1)))
            pixels.append((y, x))
            
        # Draw lines between nodes
        for idx in range(len(pixels) - 1):
            y0, x0 = pixels[idx]
            y1, x1 = pixels[idx+1]
            for py, px in bresenham_line(x0, y0, x1, y1, (h, w)):
                road_mask[py, px] = 1
                
    # If no roads were rasterized at all, mark a single center pixel to avoid EDT errors
    if not road_mask.any():
        road_mask[h // 2, w // 2] = 1
        
    # Distance transform (EDT)
    # distance_transform_edt computes distances to 0s, so we invert the mask
    dist_grid = distance_transform_edt(road_mask == 0)
    return dist_grid
