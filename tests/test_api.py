"""
API-level integration tests for app.py endpoints.
Uses FastAPI TestClient (backed by httpx).
"""
import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/zones
# ---------------------------------------------------------------------------

def test_zones_returns_list():
    resp = client.get("/api/zones")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_zones_schema():
    """Every zone object must have the required fields."""
    resp = client.get("/api/zones")
    assert resp.status_code == 200
    required = {"key", "name", "bbox", "center", "years",
                "latest_grade", "latest_abi", "overall_abi_change_pct",
                "cropland_loss_ha", "encroachment_alert"}
    for zone in resp.json():
        assert required.issubset(zone.keys()), f"Missing keys in zone {zone.get('key')}"


def test_zones_bbox_shape():
    """Each bbox must be a list of 4 floats [west, south, east, north]."""
    resp = client.get("/api/zones")
    for zone in resp.json():
        bbox = zone["bbox"]
        assert isinstance(bbox, list) and len(bbox) == 4


def test_zones_cache_control_header():
    """GET /api/zones should include a Cache-Control header."""
    resp = client.get("/api/zones")
    assert "cache-control" in {k.lower() for k in resp.headers}


# ---------------------------------------------------------------------------
# GET /api/analyse
# ---------------------------------------------------------------------------

def test_analyse_known_zone():
    """Should return 200 for a known zone with default years."""
    resp = client.get("/api/analyse?zone=bengaluru")
    assert resp.status_code == 200
    data = resp.json()
    assert "zone_info" in data
    assert "metrics" in data
    assert "timeseries" in data
    assert "transitions" in data


def test_analyse_schema():
    resp = client.get("/api/analyse?zone=nashik_north")
    assert resp.status_code == 200
    data = resp.json()
    metrics = data["metrics"]
    assert "latest_abi" in metrics
    assert "grade" in metrics
    assert "encroachment_alert" in metrics
    assert isinstance(metrics["latest_abi"], (int, float))
    assert not isinstance(metrics["latest_abi"], bool)  # must not be boolean


def test_analyse_unknown_zone_returns_404():
    resp = client.get("/api/analyse?zone=nonexistent_zone_xyz")
    assert resp.status_code == 404


def test_analyse_year_selection():
    """Explicitly providing before/after years should work and not raise."""
    resp = client.get("/api/analyse?zone=nashik_north&before=2017&after=2025")
    assert resp.status_code == 200
    data = resp.json()
    assert data["comparison"]["before_year"] == 2017
    assert data["comparison"]["after_year"] == 2025


def test_analyse_swapped_years_are_corrected():
    """If before > after, the backend should swap them and still return 200."""
    resp = client.get("/api/analyse?zone=nashik_north&before=2025&after=2017")
    assert resp.status_code == 200
    data = resp.json()
    # After swapping, before_year < after_year
    assert data["comparison"]["before_year"] < data["comparison"]["after_year"]


def test_analyse_timeseries_has_numeric_abi():
    """All timeseries records must have finite numeric ABI values."""
    resp = client.get("/api/analyse?zone=bengaluru")
    assert resp.status_code == 200
    for rec in resp.json()["timeseries"]:
        abi = rec["abi"]
        assert isinstance(abi, (int, float)), f"Non-numeric ABI: {abi!r}"
        assert abi != float("inf"), "ABI must not be Infinity in API response"
        assert abi == abi, "ABI must not be NaN"  # NaN != NaN


def test_analyse_transitions_are_five_classes():
    resp = client.get("/api/analyse?zone=hubli_outskirts")
    assert resp.status_code == 200
    transitions = resp.json()["transitions"]
    assert len(transitions) == 5
    class_names = {t["class_name"] for t in transitions}
    assert "Buildings" in class_names
    assert "Cropland" in class_names
