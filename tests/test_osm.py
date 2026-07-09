"""
tests/test_osm.py

Unit tests for OpenStreetMap fetching, rasterization, and road proximity grid calculation.
"""

import numpy as np
from pipeline.osm_fetcher import bresenham_line, get_road_proximity_grid


def test_bresenham_line():
    # Horizontal line
    pts = bresenham_line(0, 0, 5, 0, (10, 10))
    assert (0, 0) in pts
    assert (0, 5) in pts
    assert len(pts) == 6

    # Vertical line
    pts = bresenham_line(0, 0, 0, 5, (10, 10))
    assert (0, 0) in pts
    assert (5, 0) in pts
    assert len(pts) == 6

    # Diagonal line
    pts = bresenham_line(0, 0, 5, 5, (10, 10))
    assert (0, 0) in pts
    assert (5, 5) in pts
    assert len(pts) == 6


def test_get_road_proximity_grid():
    # Run in a dummy zone to trigger the fallback diagonal line generation
    # BBox values: [lon_min, lat_min, lon_max, lat_max]
    bbox = [73.0, 15.0, 73.1, 15.1]
    shape = (128, 128)
    
    # We pass an invalid zone_key to force it to fail or skip cache
    # and hit the fallback path (since we aren't mock-intercepting network requests)
    dist_grid = get_road_proximity_grid("dummy_test_zone_99", bbox, shape)
    
    assert isinstance(dist_grid, np.ndarray)
    assert dist_grid.shape == shape
    assert dist_grid.dtype == np.float64
    
    # The minimum distance should be exactly 0.0 (at the road pixels)
    assert np.isclose(dist_grid.min(), 0.0)
