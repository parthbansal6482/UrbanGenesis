import numpy as np
import pytest
from analytics.encroachment import calculate_encroachment_stats, generate_encroachment_heatmap


# ---------------------------------------------------------------------------
# calculate_encroachment_stats
# ---------------------------------------------------------------------------

def test_encroachment_stats_no_change():
    """Identical masks: zero encroachment."""
    mask = np.array([[2, 2], [4, 3]], dtype=np.uint8)
    stats = calculate_encroachment_stats(mask, mask, mapping_type="esri")
    assert stats["total_cropland_lost_ha"] == 0.0
    assert stats["total_water_lost_ha"] == 0.0


def test_encroachment_stats_full_cropland_loss():
    """
    ESRI mapping: class 2 = cropland, class 1 = buildings.
    All 4 cropland pixels become buildings → 4 * 0.01 ha = 0.04 ha lost.
    """
    before = np.full((2, 2), 2, dtype=np.uint8)  # all cropland
    after  = np.full((2, 2), 1, dtype=np.uint8)  # all buildings
    stats = calculate_encroachment_stats(before, after, mapping_type="esri")
    assert np.isclose(stats["total_cropland_lost_ha"], 0.04)
    assert stats["total_water_lost_ha"] == 0.0


def test_encroachment_stats_water_loss():
    """
    ESRI mapping: class 4 = water, class 1 = buildings.
    2 water pixels → buildings: 2 * 0.01 = 0.02 ha.
    """
    before = np.array([[4, 4], [2, 2]], dtype=np.uint8)
    after  = np.array([[1, 1], [2, 2]], dtype=np.uint8)
    stats = calculate_encroachment_stats(before, after, mapping_type="esri")
    assert np.isclose(stats["total_water_lost_ha"], 0.02)
    assert stats["total_cropland_lost_ha"] == 0.0


def test_encroachment_stats_shape_mismatch_raises():
    a = np.zeros((2, 2), dtype=np.uint8)
    b = np.zeros((3, 3), dtype=np.uint8)
    with pytest.raises(AssertionError):
        calculate_encroachment_stats(a, b)


# ---------------------------------------------------------------------------
# generate_encroachment_heatmap
# ---------------------------------------------------------------------------

def test_heatmap_output_shape_and_dtype():
    before = np.array([[2, 4], [3, 1]], dtype=np.uint8)
    after  = np.array([[1, 1], [1, 1]], dtype=np.uint8)
    heatmap = generate_encroachment_heatmap(before, after, mapping_type="esri")
    assert heatmap.shape == (2, 2, 3)
    assert heatmap.dtype == np.uint8


def test_heatmap_cropland_lost_is_red():
    """Pixels that were cropland (2) and became buildings (1) → red [239,68,68]."""
    before = np.array([[2]], dtype=np.uint8)
    after  = np.array([[1]], dtype=np.uint8)
    heatmap = generate_encroachment_heatmap(before, after, mapping_type="esri")
    np.testing.assert_array_equal(heatmap[0, 0], [239, 68, 68])


def test_heatmap_water_lost_is_cyan():
    """Pixels that were water (4) and became buildings (1) → cyan [6,182,212]."""
    before = np.array([[4]], dtype=np.uint8)
    after  = np.array([[1]], dtype=np.uint8)
    heatmap = generate_encroachment_heatmap(before, after, mapping_type="esri")
    np.testing.assert_array_equal(heatmap[0, 0], [6, 182, 212])


def test_heatmap_existing_infra_is_slate():
    """Pixels that were buildings (1) and stayed buildings (1) → slate [71,85,105]."""
    before = np.array([[1]], dtype=np.uint8)
    after  = np.array([[1]], dtype=np.uint8)
    heatmap = generate_encroachment_heatmap(before, after, mapping_type="esri")
    np.testing.assert_array_equal(heatmap[0, 0], [71, 85, 105])


def test_heatmap_unchanged_background_is_dark():
    """Unchanged non-infrastructure pixels → dark background [15,23,42]."""
    before = np.array([[3]], dtype=np.uint8)  # dense vegetation
    after  = np.array([[3]], dtype=np.uint8)
    heatmap = generate_encroachment_heatmap(before, after, mapping_type="esri")
    np.testing.assert_array_equal(heatmap[0, 0], [15, 23, 42])
