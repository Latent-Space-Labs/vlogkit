"""/projects CRUD."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_registry
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import (
    ErrorDetail,
    ProjectEntryResponse,
    RegisterProjectRequest,
)


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects",
        tags=["projects"],
        dependencies=[Depends(require_token)],
    )

    @router.get("", response_model=list[ProjectEntryResponse])
    def list_projects(
        registry: ProjectRegistry = Depends(get_registry),
    ) -> list[ProjectEntryResponse]:
        return [ProjectEntryResponse(**e.__dict__) for e in registry.list()]

    @router.post(
        "",
        response_model=ProjectEntryResponse,
        status_code=status.HTTP_201_CREATED,
        responses={404: {"model": ErrorDetail}},
    )
    def register_project(
        body: RegisterProjectRequest,
        request: Request,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> ProjectEntryResponse:
        folder = Path(body.path)
        if not folder.is_dir():
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    code="project_path_not_found",
                    message=f"Folder does not exist: {folder}",
                ).model_dump(),
            )
        entry = registry.register(folder)
        # Populate the clip index so /media can resolve hashes without scanning.
        from vlogkit.project import Project
        project = Project(root=folder)
        request.app.state.clip_index.add_project(entry.id, project)
        return ProjectEntryResponse(**entry.__dict__)

    @router.get(
        "/{project_id}",
        response_model=ProjectEntryResponse,
        responses={404: {"model": ErrorDetail}},
    )
    def get_project(
        project_id: str,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> ProjectEntryResponse:
        entry = registry.get(project_id)
        if not entry:
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    code="project_not_found",
                    message=f"Unknown project: {project_id}",
                ).model_dump(),
            )
        return ProjectEntryResponse(**entry.__dict__)

    @router.delete(
        "/{project_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        responses={404: {"model": ErrorDetail}},
    )
    def forget_project(
        project_id: str,
        request: Request,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> None:
        if not registry.forget(project_id):
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    code="project_not_found",
                    message=f"Unknown project: {project_id}",
                ).model_dump(),
            )
        request.app.state.clip_index.remove_project(project_id)

    return router
