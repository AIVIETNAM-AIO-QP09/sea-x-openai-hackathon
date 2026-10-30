"""Aggregate router mounted at ``/api/v1``. Each group in 08 §2 adds its own
module here (``app/api/<group>.py``) and is included below."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import health

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(health.router)
