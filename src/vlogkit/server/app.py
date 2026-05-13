"""FastAPI app factory for the vlogkit desktop/companion server."""
from __future__ import annotations

import socket
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vlogkit.project import Project
from vlogkit.server.clip_index import ClipIndex
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.routes import health, uploads
from vlogkit.server.routes import analyze as analyze_routes
from vlogkit.server.routes import clips as clips_routes
from vlogkit.server.routes import export as export_routes
from vlogkit.server.routes import projects as projects_routes
from vlogkit.server.routes import search as search_routes
from vlogkit.server.routes import storyboard as storyboard_routes
from vlogkit.server.ws import WsBroker


def create_app(project: Project, token: str) -> FastAPI:
    """Build the FastAPI app.

    Args:
        project: Project whose files are served/managed.
        token: Shared-secret bearer token required on all non-health requests.
    """
    app = FastAPI(title="vlogkit server")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Stash shared state on app.state for dependencies to read.
    app.state.project = project
    app.state.token = token

    app.include_router(health.create_router())
    app.include_router(uploads.create_router(project))

    return app


def create_desktop_app(registry_path: Path, token: str) -> FastAPI:
    """Build the FastAPI app for desktop mode.

    Unlike ``create_app``, this one manages many projects via a registry
    and is the entrypoint used by the Electron shell.
    """
    app = FastAPI(title="vlogkit desktop server")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.registry = ProjectRegistry(registry_path)
    app.state.clip_index = ClipIndex()
    app.state.ws_broker = WsBroker()
    app.state.token = token

    # Seed the clip index for any projects already in the registry so that
    # /media/{hash} works immediately after a sidecar restart (without the
    # user having to re-open the folder via POST /projects).
    def _seed_clip_index() -> None:
        registry: ProjectRegistry = app.state.registry
        index: ClipIndex = app.state.clip_index
        for entry in registry.list():
            try:
                project = Project(root=Path(entry.path))
                index.add_project(entry.id, project)
            except Exception:
                pass  # missing folder etc — skip silently

    threading.Thread(target=_seed_clip_index, daemon=True).start()

    app.include_router(health.create_router())
    app.include_router(projects_routes.create_router())
    app.include_router(clips_routes.create_router())
    app.include_router(clips_routes.create_media_router())
    app.include_router(analyze_routes.create_router())
    app.include_router(storyboard_routes.create_router())
    app.include_router(search_routes.create_router())
    app.include_router(export_routes.create_router())

    return app


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def run_server(
    project: Project,
    token: str,
    host: str = "127.0.0.1",
    port: int = 8420,
) -> None:
    """Run the server (used by `vlogkit serve` and `vlogkit server`)."""
    import uvicorn

    app = create_app(project=project, token=token)
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_desktop_server(
    registry_path: Path,
    token: str,
    host: str = "127.0.0.1",
    port: int = 0,
) -> None:
    """Run the desktop-mode server (used by Electron sidecar)."""
    import uvicorn

    app = create_desktop_app(registry_path=registry_path, token=token)
    uvicorn.run(app, host=host, port=port, log_level="warning")
