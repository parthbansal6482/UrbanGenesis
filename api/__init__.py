"""
api — FastAPI HTTP layer for the FarmGuard/UrbanGenesis platform.

Exposes two endpoints:
    GET /api/zones    — list of configured geographic zones with summary metrics
    GET /api/analyse  — detailed zone analysis with timeseries, transitions,
                        overlays, and dynamic encroachment heatmap

The application factory is ``api.main.create_app()``.
``app.py`` at the project root is a thin shim that calls ``create_app()``
so all existing run commands remain unchanged.
"""
