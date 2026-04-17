"""GET /healthz — unauthenticated liveness probe."""
from __future__ import annotations

from fastapi import APIRouter

from vlogkit import __version__ as _version_or_none


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "version": _version_or_none or "0.0.0",
        }

    return router
