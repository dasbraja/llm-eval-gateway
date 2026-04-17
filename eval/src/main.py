"""
main.py
-------
Application entry point.

Wires together the FastAPI instance (bootstrap.py) and all routes (router.py).
Also mounts the /health check directly on the app.

Run
---
uvicorn main:app --reload
"""

from __future__ import annotations

import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

from src.bootstrap import app
from src.router import router

# Register all /api/* routes
app.include_router(router)


# ── Health check ──────────────────────────────
import os

@app.get("/health", tags=["meta"], summary="Health check")
def health() -> dict:
    return {
        "status": "ok",
        "judge_model": os.environ.get("JUDGE_MODEL", "gemini-2.5-flash"),
        "gcp_project": os.environ.get("GCP_PROJECT", "your-project-name"),
        "gcp_location": os.environ.get("GCP_LOCATION", "us-central1"),
    }