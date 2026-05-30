"""POST /projects/{id}/render — async; renders a finished MP4 in a background thread."""

from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, Depends, status

from vlogkit.project import Project
from vlogkit.server import jobs as jobs_module
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_broker, get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail, RenderRequest
from vlogkit.server.ws import WsBroker


def _run_job_in_thread(
    broker: WsBroker,
    project_id: str,
    project: Project,
    job_id: str,
    captions: bool,
    resolution: str | None,
    fps: float | None,
) -> threading.Thread:
    """Spawn a thread running the coroutine on its own fresh event loop.

    Same pattern as score.py / analyze.py — TestClient-friendly and safe under
    uvicorn.
    """

    def target() -> None:
        asyncio.run(
            jobs_module.run_render_job(
                broker,
                project_id,
                project,
                job_id,
                captions=captions,
                resolution=resolution,
                fps=fps,
            )
        )

    t = threading.Thread(target=target, daemon=True, name=f"render-{job_id[:8]}")
    t.start()
    return t


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["render"],
        dependencies=[Depends(require_token)],
    )

    @router.post(
        "/render",
        status_code=status.HTTP_202_ACCEPTED,
        responses={404: {"model": ErrorDetail}},
    )
    async def start_render(
        project_id: str,
        body: RenderRequest,
        registry: ProjectRegistry = Depends(get_registry),
        broker: WsBroker = Depends(get_broker),
    ) -> dict[str, str]:
        project = load_project(registry, project_id)
        job_id = jobs_module.new_job_id()
        _run_job_in_thread(
            broker,
            project_id,
            project,
            job_id,
            body.captions,
            body.resolution,
            body.fps,
        )
        return {"job_id": job_id}

    return router
