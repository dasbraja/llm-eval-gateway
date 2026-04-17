"""
router.py
---------
Central router: imports every sub-router and registers them under /api.
Add new route modules here — bootstrap.py and main.py never need to change.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.api.pairwise import router as pairwise_router
from src.api.pointwise import router as pointwise_router

router = APIRouter(prefix="/api")

router.include_router(pointwise_router, tags=["pointwise"])
router.include_router(pairwise_router, tags=["pairwise"])