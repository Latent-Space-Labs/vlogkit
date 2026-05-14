"""POST /projects/{id}/score — runs Murch scoring synchronously."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from vlogkit.score import scorer as scorer_module
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail


def create_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/projects/{project_id}/score",
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(require_token)],
        responses={404: {"model": ErrorDetail}},
    )
    async def start_score(
        project_id: str,
        force: bool = False,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> dict[str, int]:
        project = load_project(registry, project_id)
        scored = scorer_module.run_scoring(project, force=force)
        return {"scored": scored}

    return router
