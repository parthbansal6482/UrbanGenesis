"""
tests/test_api.py

Smoke tests for the FarmGuard FastAPI routes.

Uses FastAPI's built-in TestClient (backed by httpx) — no running server needed.
These tests verify that the API contract is stable after the refactor:
    - Endpoints respond with the expected HTTP status codes
    - Response payloads carry the mandatory top-level keys
    - Zone whitelist enforcement rejects unknown keys with 404
    - Before/after year swapping is handled silently (no 5xx)

Note: tests run against the API in demo mode. If ``demo/precomputed/``
exists on disk the tests exercise real verdict loading; if it is absent
the fallback verdict path is exercised instead — both branches are valid.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Create a TestClient for the full app, reused across all tests in this module."""
    app = create_app()
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# GET /api/zones
# ---------------------------------------------------------------------------


class TestGetZones:
    def test_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/zones")
        assert response.status_code == 200

    def test_response_is_list(self, client: TestClient) -> None:
        response = client.get("/api/zones")
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_each_zone_has_required_keys(self, client: TestClient) -> None:
        required_keys = {
            "key", "name", "bbox", "center", "years",
            "satyukt_relevance", "latest_grade", "latest_abi",
            "overall_abi_change_pct", "cropland_loss_ha", "encroachment_alert",
        }
        data = client.get("/api/zones").json()
        for zone in data:
            missing = required_keys - set(zone.keys())
            assert not missing, f"Zone '{zone.get('key')}' missing keys: {missing}"

    def test_bbox_is_four_element_list(self, client: TestClient) -> None:
        data = client.get("/api/zones").json()
        for zone in data:
            assert len(zone["bbox"]) == 4, f"Zone '{zone['key']}' bbox should have 4 elements"

    def test_center_is_lat_lon(self, client: TestClient) -> None:
        data = client.get("/api/zones").json()
        for zone in data:
            assert len(zone["center"]) == 2, f"Zone '{zone['key']}' center should be [lat, lon]"

    def test_cache_control_header_present(self, client: TestClient) -> None:
        response = client.get("/api/zones")
        assert "cache-control" in response.headers

    def test_known_zones_are_present(self, client: TestClient) -> None:
        """All four configured zones must appear in the response."""
        data = client.get("/api/zones").json()
        keys = {z["key"] for z in data}
        expected = {"nashik_north", "vijayawada_west", "hubli_outskirts", "bengaluru"}
        assert expected.issubset(keys), f"Missing zones: {expected - keys}"


# ---------------------------------------------------------------------------
# GET /api/analyse
# ---------------------------------------------------------------------------


class TestAnalyseZone:
    def test_returns_200_for_valid_zone(self, client: TestClient) -> None:
        response = client.get("/api/analyse", params={"zone": "nashik_north"})
        assert response.status_code == 200

    def test_returns_404_for_unknown_zone(self, client: TestClient) -> None:
        response = client.get("/api/analyse", params={"zone": "nonexistent_zone"})
        assert response.status_code == 404

    def test_response_has_top_level_keys(self, client: TestClient) -> None:
        data = client.get("/api/analyse", params={"zone": "nashik_north"}).json()
        required = {"zone_info", "metrics", "comparison", "transitions", "timeseries", "overlays"}
        missing = required - set(data.keys())
        assert not missing, f"Missing top-level keys: {missing}"

    def test_metrics_has_grade_and_abi(self, client: TestClient) -> None:
        data = client.get("/api/analyse", params={"zone": "nashik_north"}).json()
        metrics = data["metrics"]
        assert "grade" in metrics
        assert "latest_abi" in metrics
        assert "cropland_loss_ha" in metrics
        assert "encroachment_alert" in metrics

    def test_comparison_has_before_after_years(self, client: TestClient) -> None:
        data = client.get("/api/analyse", params={"zone": "nashik_north"}).json()
        comp = data["comparison"]
        assert "before_year" in comp
        assert "after_year" in comp
        assert comp["before_year"] <= comp["after_year"]

    def test_transitions_is_non_empty_list(self, client: TestClient) -> None:
        data = client.get("/api/analyse", params={"zone": "nashik_north"}).json()
        transitions = data["transitions"]
        assert isinstance(transitions, list)
        assert len(transitions) > 0

    def test_each_transition_has_required_keys(self, client: TestClient) -> None:
        data = client.get("/api/analyse", params={"zone": "nashik_north"}).json()
        required = {"class_id", "class_name", "before_pct", "after_pct", "trend_shift_pct", "status"}
        for t in data["transitions"]:
            missing = required - set(t.keys())
            assert not missing, f"Transition missing keys: {missing}"

    def test_timeseries_is_list_with_abi(self, client: TestClient) -> None:
        data = client.get("/api/analyse", params={"zone": "nashik_north"}).json()
        ts = data["timeseries"]
        assert isinstance(ts, list) and len(ts) > 0
        for rec in ts:
            assert "year" in rec
            assert "abi" in rec
            assert isinstance(rec["abi"], float)

    def test_overlays_has_before_and_after(self, client: TestClient) -> None:
        data = client.get("/api/analyse", params={"zone": "nashik_north"}).json()
        overlays = data["overlays"]
        assert "before" in overlays
        assert "after" in overlays
        assert "encroachment_heatmap" in overlays

    def test_swapped_years_do_not_500(self, client: TestClient) -> None:
        """Passing before > after should be silently corrected, not cause a server error."""
        response = client.get(
            "/api/analyse",
            params={"zone": "nashik_north", "before": 2023, "after": 2017},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["comparison"]["before_year"] <= data["comparison"]["after_year"]

    def test_all_zones_respond_200(self, client: TestClient) -> None:
        """Every configured zone should return a valid 200 response."""
        zones = client.get("/api/zones").json()
        for zone in zones:
            resp = client.get("/api/analyse", params={"zone": zone["key"]})
            assert resp.status_code == 200, (
                f"Zone '{zone['key']}' returned {resp.status_code}: {resp.text[:200]}"
            )

    def test_abi_is_finite_float(self, client: TestClient) -> None:
        """ABI values in timeseries should never be NaN or Infinity."""
        import math
        data = client.get("/api/analyse", params={"zone": "nashik_north"}).json()
        for rec in data["timeseries"]:
            abi = rec["abi"]
            assert math.isfinite(abi), f"Non-finite ABI in year {rec['year']}: {abi}"


# ---------------------------------------------------------------------------
# Core module tests
# ---------------------------------------------------------------------------


class TestCoreModules:
    def test_class_map_has_six_classes(self) -> None:
        from core.class_map import CLASS_INFO, CLASS_COLORS, CLASS_RGB

        assert len(CLASS_INFO) == 6
        assert len(CLASS_COLORS) == 6
        assert len(CLASS_RGB) == 6

    def test_esri_to_farmguard_values_in_range(self) -> None:
        from core.class_map import ESRI_TO_FARMGUARD, CLASS_INFO

        valid_ids = set(CLASS_INFO.keys())
        for esri_cls, fg_cls in ESRI_TO_FARMGUARD.items():
            assert fg_cls in valid_ids, (
                f"ESRI class {esri_cls} maps to invalid FarmGuard class {fg_cls}"
            )

    def test_rgb_to_mask_roundtrip(self) -> None:
        """rgb_to_mask(mask_to_rgb(mask)) should recover the original mask."""
        import numpy as np
        from core.utils.image_utils import mask_to_rgb, rgb_to_mask

        original = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.uint8)
        rgb = mask_to_rgb(original)
        recovered = rgb_to_mask(rgb)
        np.testing.assert_array_equal(original, recovered)

    def test_config_loads_zones(self) -> None:
        from core.config import ZONES_CONFIG

        assert "nashik_north" in ZONES_CONFIG
        assert "bbox" in ZONES_CONFIG["nashik_north"]

    def test_forecast_bbox_endpoint(self, client: TestClient, monkeypatch) -> None:
        # Mock forecast_zone to avoid running U-Net model on CPU during tests
        called = []
        def mock_forecast_zone(*args, **kwargs):
            called.append(args)
            # Create a mock verdict.json inside cached custom zone directory
            import json
            zone_dir = kwargs.get("zone_dir")
            zone_dir.mkdir(parents=True, exist_ok=True)
            # Write mock verdict
            mock_verdict = {
                "zone": "bbox_-122.1_37.2_-122.0_37.3",
                "grade": "B",
                "abi": 0.8,
                "cropland_loss_ha": 0.0,
                "timeseries": [
                    {"year": 2017, "abi": 0.9, "cropland_pixels": 100, "buildings_pixels": 10, "vegetation_pixels": 10, "water_pixels": 10, "soil_pixels": 10, "cropland_pct": 10, "buildings_pct": 10, "vegetation_pct": 10, "water_pct": 10, "soil_pct": 10},
                    {"year": 2019, "abi": 0.88, "cropland_pixels": 100, "buildings_pixels": 10, "vegetation_pixels": 10, "water_pixels": 10, "soil_pixels": 10, "cropland_pct": 10, "buildings_pct": 10, "vegetation_pct": 10, "water_pct": 10, "soil_pct": 10},
                    {"year": 2021, "abi": 0.85, "cropland_pixels": 100, "buildings_pixels": 10, "vegetation_pixels": 10, "water_pixels": 10, "soil_pixels": 10, "cropland_pct": 10, "buildings_pct": 10, "vegetation_pct": 10, "water_pct": 10, "soil_pct": 10},
                    {"year": 2023, "abi": 0.82, "cropland_pixels": 100, "buildings_pixels": 10, "vegetation_pixels": 10, "water_pixels": 10, "soil_pixels": 10, "cropland_pct": 10, "buildings_pct": 10, "vegetation_pct": 10, "water_pct": 10, "soil_pct": 10},
                    {"year": 2025, "abi": 0.8, "cropland_pixels": 100, "buildings_pixels": 10, "vegetation_pixels": 10, "water_pixels": 10, "soil_pixels": 10, "cropland_pct": 10, "buildings_pct": 10, "vegetation_pct": 10, "water_pct": 10, "soil_pct": 10},
                    {"year": 2041, "abi": 0.8, "cropland_pixels": 100, "buildings_pixels": 10, "vegetation_pixels": 10, "water_pixels": 10, "soil_pixels": 10, "cropland_pct": 10, "buildings_pct": 10, "vegetation_pct": 10, "water_pct": 10, "soil_pct": 10},
                ]
            }
            # Touch mask_rgb_2041.png
            (zone_dir / "mask_rgb_2041.png").touch()
            with open(zone_dir / "verdict.json", "w") as f:
                json.dump(mock_verdict, f)

        monkeypatch.setattr("model.forecast.forecast_zone", mock_forecast_zone)

        payload = {
            "min_lon": -122.1,
            "min_lat": 37.2,
            "max_lon": -122.0,
            "max_lat": 37.3,
            "years": [2017, 2041],
            "force_refresh": True
        }
        response = client.post("/api/forecast_bbox", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["zone_info"]["years"] == [2017, 2019, 2021, 2023, 2025, 2041]
        assert data["metrics"]["grade"] == "C"
        assert len(called) == 1
