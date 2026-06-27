"""
api/main.py

FastAPI application factory for the FarmGuard/UrbanGenesis platform.

Call ``create_app()`` to obtain a fully configured ``FastAPI`` instance
with CORS, cache-control middleware, static file mounting, and all API
routers registered.

The project-root ``app.py`` is a thin shim that does:
    from api.main import create_app
    app = create_app()
so that all existing run commands (``python app.py``,
``UVICORN_RELOAD=true PYTHONPATH=. python app.py``) remain unchanged.
"""

import logging
import os
import socket

# Prevent long network hangs on on-demand dynamic custom bboxes using robust GDAL config
os.environ["GDAL_HTTP_TIMEOUT"] = "30"
os.environ["GDAL_HTTP_CONNECTTIMEOUT"] = "15"
os.environ["GDAL_HTTP_MAX_RETRY"] = "5"
os.environ["GDAL_HTTP_RETRY_DELAY"] = "2"

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes.analyse import router as analyse_router
from api.routes.zones import router as zones_router
from core.config import PRECOMPUTED_DIR

logger = logging.getLogger(__name__)


def _get_cors_origins() -> list[str]:
    """
    Resolve the allowed CORS origins from the environment.

    Production deployments should set CORS_ORIGINS to a comma-separated
    list of origins (e.g. ``https://farmguard.satyukt.com``).
    Defaults to localhost for local development.
    """
    env_val = os.getenv("CORS_ORIGINS", "")
    if env_val:
        return [o.strip() for o in env_val.split(",") if o.strip()]
    return ["http://localhost:3000", "http://127.0.0.1:3000"]


def create_app() -> FastAPI:
    """
    Create and return the configured FastAPI application.

    Middleware stack (outermost → innermost):
        1. CORSMiddleware     — env-driven origin whitelist
        2. Cache-Control      — 24-h immutable cache for /static/* assets

    Routes:
        GET /api/zones   — api.routes.zones
        GET /api/analyse — api.routes.analyse
        /static/*        — StaticFiles (demo/precomputed/)
    """
    application = FastAPI(
        title="UrbanGenesis API",
        description="Backend API for Satyukt Farmland Encroachment Detection System",
        version="1.0.0",
    )

    # ------------------------------------------------------------------
    # CORS — must be added before other middleware so preflight requests
    # are handled before any custom middleware intercepts them.
    # ------------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Cache-Control for precomputed static assets
    # ------------------------------------------------------------------
    @application.middleware("http")
    async def add_cache_control(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") and response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=86400, immutable"
        return response

    # ------------------------------------------------------------------
    # Static files — serve precomputed PNGs and JSONs
    # ------------------------------------------------------------------
    if PRECOMPUTED_DIR.exists():
        application.mount(
            "/static",
            StaticFiles(directory=str(PRECOMPUTED_DIR)),
            name="static",
        )
        logger.info("Mounted static directory: %s", PRECOMPUTED_DIR)
    else:
        logger.warning("Precomputed directory does not exist: %s", PRECOMPUTED_DIR)

    # ------------------------------------------------------------------
    # API routers
    # ------------------------------------------------------------------
    application.include_router(zones_router)
    application.include_router(analyse_router)

    return application
