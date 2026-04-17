"""/projects/{id}/analyze + /projects/{id}/events (WebSocket)."""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)

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
) -> threading.Thread:
    """Spawn a thread running the coroutine on its own fresh event loop.

    Why not ``asyncio.create_task``? Under Starlette's TestClient each HTTP
    request runs in its own AnyIO portal with its own loop, which is torn
    down when the handler returns — cancelling any task scheduled on it.
    A dedicated thread with its own loop survives the POST, and the WS
    broker uses ``call_soon_threadsafe`` to deliver events into the WS's
    loop. Under uvicorn this is also fine — one extra thread per job.
    """

    def target() -> None:
        asyncio.run(
            jobs_module.run_analyze_job(broker, project_id, project, job_id)
        )

    t = threading.Thread(target=target, daemon=True, name=f"analyze-{job_id[:8]}")
    t.start()
    return t


def create_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/projects/{project_id}/analyze",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_token)],
        responses={404: {"model": ErrorDetail}},
    )
    async def start_analyze(
        project_id: str,
        registry: ProjectRegistry = Depends(get_registry),
        broker: WsBroker = Depends(get_broker),
    ) -> dict[str, str]:
        project = load_project(registry, project_id)
        job_id = jobs_module.new_job_id()
        _run_job_in_thread(broker, project_id, project, job_id)
        return {"job_id": job_id}

    @router.websocket("/projects/{project_id}/events")
    async def events_ws(ws: WebSocket, project_id: str) -> None:
        token = ws.query_params.get("token")
        if token != ws.app.state.token:
            await ws.close(code=1008)
            return
        await ws.accept()
        broker: WsBroker = ws.app.state.ws_broker
        q = broker.subscribe(project_id)
        try:
            while True:
                evt = await q.get()
                await ws.send_json(evt.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        finally:
            broker.unsubscribe(project_id, q)

    return router
