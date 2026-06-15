import numpy as np
import pytest
from analytics.change_detection import (
    compute_transition_matrix,
    detect_urban_expansion,
    compute_cropland_loss_ha,
)
from analytics.abi import compute_abi
from analytics.grader import assign_grade, detect_encroachment_alert, generate_verdict

def test_transition_matrix():
    mask_before = np.array([[2, 2], [1, 1]], dtype=np.uint8)
    mask_after  = np.array([[1, 2], [1, 1]], dtype=np.uint8)
    
    matrix = compute_transition_matrix(mask_before, mask_after, num_classes=6)
    
    # Verify shape
    assert matrix.shape == (6, 6)
    # Check transitions
    assert matrix[2, 1] == 1  # 1 pixel of class 2 changed to class 1
    assert matrix[2, 2] == 1  # 1 pixel of class 2 stayed class 2
    assert matrix[1, 1] == 2  # 2 pixels of class 1 stayed class 1
    assert matrix.sum() == 4  # Total pixels

def test_detect_urban_expansion_metrics():
    # 2=cropland, 3=vegetation, 4=water (buffer)
    # 1=buildings (encroachment)
    mask_before = np.array([[2, 3], [4, 1]], dtype=np.uint8)
    mask_after  = np.array([[1, 1], [1, 1]], dtype=np.uint8)
    
    metrics = detect_urban_expansion(mask_before, mask_after)
    
    assert metrics["buffer_to_encroachment_loss_pixels"] == 3
    assert metrics["buffer_to_encroachment_loss_pct"] == 75.0
    assert metrics["infrastructure_net_increase_pixels"] == 3
    assert metrics["infrastructure_growth_pct"] == 300.0

def test_compute_cropland_loss_ha():
    # resolution_m = 10m. 1 pixel = 100 m2. 100 pixels = 10000 m2 = 1.0 ha
    mask_before = np.zeros((10, 10), dtype=np.uint8)
    mask_before[:, :] = 2  # 100 cropland pixels
    
    mask_after = np.zeros((10, 10), dtype=np.uint8)
    mask_after[:, :] = 2  # start with all cropland pixels
    mask_after[0, :] = 1  # 10 buildings, 90 cropland remaining
    
    loss = compute_cropland_loss_ha(mask_before, mask_after, resolution_m=10.0)
    assert np.isclose(loss, 0.10)  # 10 pixels lost = 1000 m2 = 0.1 ha

def test_abi_calculation():
    # 2=cropland, 3=veg, 4=water, 1=buildings, 5=soil, 0=bg
    mask = np.array([
        [2, 2, 3],
        [4, 1, 1],
        [5, 0, 0]
    ], dtype=np.uint8)
    
    # buffer pixels: 2, 2, 3, 4 (total 4)
    # encroach pixels: 1, 1 (total 2)
    # ABI = 4 / 2 = 2.0
    res = compute_abi(mask)
    assert res["abi"] == 2.0
    assert res["cropland_pixels"] == 2
    assert res["encroach_pixels"] == 2

def test_grader_thresholds():
    assert assign_grade(2.5)["grade"] == "A"
    assert assign_grade(1.5)["grade"] == "B"
    assert assign_grade(0.7)["grade"] == "C"
    assert assign_grade(0.4)["grade"] == "D"
    assert assign_grade(0.1)["grade"] == "F"

def test_encroachment_alert_detection():
    ts = [
        {"year": 2017, "abi": 1.0},
        {"year": 2019, "abi": 0.8},
        {"year": 2021, "abi": 0.6},
    ]
    # drop from 1.0 to 0.6 is 40% (which is >= 20%) in <= 5 years
    assert detect_encroachment_alert(ts, window_years=5, drop_threshold=0.20) is True

    # No drop
    ts_stable = [
        {"year": 2017, "abi": 1.0},
        {"year": 2021, "abi": 0.95},
    ]
    assert detect_encroachment_alert(ts_stable, window_years=5, drop_threshold=0.20) is False

def test_generate_verdict_summary():
    timeseries = [
        {"year": 2017, "abi": 1.0},
        {"year": 2019, "abi": 0.8},
        {"year": 2021, "abi": 0.6},
    ]
    verdict = generate_verdict(timeseries, "Nashik North", cropland_loss_ha=4.5)
    
    assert verdict["zone"] == "Nashik North"
    assert verdict["latest_year"] == 2021
    assert verdict["abi"] == 0.6
    assert verdict["grade"] == "C"
    assert verdict["encroachment_alert"] is True
    assert verdict["overall_abi_change_pct"] == -40.0
    assert verdict["cropland_loss_ha"] == 4.5
    assert "Encroachment Alert Active" in verdict["summary"]
