"""/projects/{id}/storyboard CRUD."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from vlogkit.models import Storyboard
from vlogkit.project import Project
from vlogkit.server.auth import require_token
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail


def _registry(request: Request) -> ProjectRegistry:
    return request.app.state.registry


def _load_project(registry: ProjectRegistry, project_id: str) -> Project:
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


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["storyboard"],
        dependencies=[Depends(require_token)],
    )

    @router.get(
        "/storyboard",
        response_model=Storyboard,
        responses={404: {"model": ErrorDetail}},
    )
    def get_storyboard(
        project_id: str,
        registry: ProjectRegistry = Depends(_registry),
    ) -> Storyboard:
        project = _load_project(registry, project_id)
        sb = project.load_storyboard()
        if sb is None:
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    code="storyboard_not_found",
                    message="No storyboard generated for this project yet",
                ).model_dump(),
            )
        return sb

    @router.put(
        "/storyboard",
        response_model=Storyboard,
        responses={404: {"model": ErrorDetail}},
    )
    def put_storyboard(
        project_id: str,
        storyboard: Storyboard,
        registry: ProjectRegistry = Depends(_registry),
    ) -> Storyboard:
        project = _load_project(registry, project_id)
        # Ensure cache dir exists before writing storyboard.json.
        project.cache_dir.mkdir(parents=True, exist_ok=True)
        project.save_storyboard(storyboard)
        return storyboard

    return router
