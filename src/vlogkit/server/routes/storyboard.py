"""/projects/{id}/storyboard CRUD."""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from vlogkit.models import Storyboard
from vlogkit.project import Project
from vlogkit.server import jobs as jobs_module
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_broker, get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail
from vlogkit.server.ws import WsBroker


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
        registry: ProjectRegistry = Depends(get_registry),
    ) -> Storyboard:
        project = load_project(registry, project_id)
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
        registry: ProjectRegistry = Depends(get_registry),
    ) -> Storyboard:
        project = load_project(registry, project_id)
        # Ensure cache dir exists before writing storyboard.json.
        project.cache_dir.mkdir(parents=True, exist_ok=True)
        project.save_storyboard(storyboard)
        return storyboard

    @router.post(
        "/storyboard/regenerate",
        status_code=status.HTTP_202_ACCEPTED,
        responses={404: {"model": ErrorDetail}},
    )
    def regenerate(
        project_id: str,
        registry: ProjectRegistry = Depends(get_registry),
        broker: WsBroker = Depends(get_broker),
    ) -> dict[str, str]:
        project = load_project(registry, project_id)
        job_id = jobs_module.new_job_id()

        def run_in_thread() -> None:
            asyncio.run(
                jobs_module.run_regenerate_job(
                    broker, project_id, project, job_id
                )
            )

        threading.Thread(
            target=run_in_thread,
            daemon=True,
            name=f"regen-{job_id[:8]}",
        ).start()
        return {"job_id": job_id}

    return router
