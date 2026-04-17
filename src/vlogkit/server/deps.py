"""Shared FastAPI dependency helpers."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request

from vlogkit.project import Project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail
from vlogkit.server.ws import WsBroker


def get_registry(request: Request) -> ProjectRegistry:
    return request.app.state.registry


def get_broker(request: Request) -> WsBroker:
    return request.app.state.ws_broker


def load_project(registry: ProjectRegistry, project_id: str) -> Project:
    entry = registry.get(project_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="project_not_found",
                message=f"Unknown project: {project_id}",
            ).model_dump(),
        )
    return Project(root=Path(entry.path))
