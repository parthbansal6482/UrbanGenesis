"""
app.py — UrbanGenesis API entry point.

This file is intentionally minimal. All application logic lives in the
``api/`` package. This shim exists solely to:
    1. Expose the ``app`` symbol that uvicorn looks up by name.
    2. Provide the ``__main__`` block for direct execution.

Run commands (unchanged from before the refactor):
    python app.py
    UVICORN_RELOAD=true PYTHONPATH=. python app.py
"""

from api.main import create_app

app = create_app()

if __name__ == "__main__":
    import os

    import uvicorn

    _dev_mode = os.getenv("UVICORN_RELOAD", "false").lower() == "true"
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=_dev_mode)
