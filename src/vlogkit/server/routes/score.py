"""POST /projects/{id}/score — async; runs Murch scoring in a background thread."""

from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, Depends, status

from vlogkit.project import Project
from vlogkit.server import jobs as jobs_module
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_broker, get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail
from vlogkit.server.ws import WsBroker


def _run_job_in_thread(
    broker: WsBroker,
    project_id: str,
    project: Project,
    job_id: str,
    force: bool,
) -> threading.Thread:
    """Spawn a thread running the coroutine on its own fresh event loop.

    Same pattern as analyze.py — TestClient-friendly and safe under uvicorn.
    """

    def target() -> None:
        asyncio.run(
            jobs_module.run_score_job(broker, project_id, project, job_id, force)
        )

    t = threading.Thread(target=target, daemon=True, name=f"score-{job_id[:8]}")
    t.start()
    return t


def create_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/projects/{project_id}/score",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_token)],
        responses={404: {"model": ErrorDetail}},
    )
    async def start_score(
        project_id: str,
        force: bool = False,
        registry: ProjectRegistry = Depends(get_registry),
        broker: WsBroker = Depends(get_broker),
    ) -> dict[str, str]:
        project = load_project(registry, project_id)
        job_id = jobs_module.new_job_id()
        _run_job_in_thread(broker, project_id, project, job_id, force)
        return {"job_id": job_id}

    return router
