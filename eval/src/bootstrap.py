"""
bootstrap.py
------------
Creates the FastAPI application instance and initialises Vertex AI.
Import `app` from here everywhere else — never instantiate FastAPI elsewhere.

Environment variables
---------------------
GCP_PROJECT   : GCP project ID (required)
GCP_LOCATION  : Vertex AI region  (default: us-central1)
JUDGE_MODEL   : Default judge model ID (default: gemini-2.0-flash-001)
GOOGLE_APPLICATION_CREDENTIALS : Path to service-account JSON (or use gcloud ADC)
"""

from __future__ import annotations

import os

import vertexai
from fastapi import FastAPI

# ── Vertex AI init ────────────────────────────
GCP_PROJECT: str = os.environ.get("GCP_PROJECT", "your-gcp-project-id")
GCP_LOCATION: str = os.environ.get("GCP_LOCATION", "us-central1")

vertexai.init(project=GCP_PROJECT, location=GCP_LOCATION)

# ── FastAPI instance ──────────────────────────
app = FastAPI(
    title="GenAI Eval Service",
    description=(
        "LLM evaluation service backed by Vertex AI. "
        "POST /api/pointwise evaluates a single response; "
        "POST /api/pairwise compares two responses (A vs B). "
        "Both endpoints accept 1–5 fully inline metric templates."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)