"""/projects/{id}/export."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from vlogkit.project import Project
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail, ExportRequest, ExportResponse


def _do_export(project: Project, fmt: str, dest: Path) -> None:
    """Adapter — real call to vlogkit.export. Monkey-patchable in tests.

    Mirrors the CLI's ``export`` command: load the Storyboard (falling back to
    storyboard.md if no JSON cache), convert to an OTIO Timeline, and write via
    ``export_timeline``.
    """
    from vlogkit.export.formats import export_timeline
    from vlogkit.export.timeline import storyboard_to_timeline

    sb = project.load_storyboard()
    if sb is None:
        sb_path = project.storyboard_path()
        if sb_path.exists():
            from vlogkit.interactive.markdown import markdown_to_storyboard

            sb = markdown_to_storyboard(
                sb_path.read_text(), project_root=project.root
            )
        else:
            raise ValueError("no storyboard")

    timeline = storyboard_to_timeline(sb)
    export_timeline(timeline, dest, fmt=fmt)


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["export"],
        dependencies=[Depends(require_token)],
    )

    @router.post(
        "/export",
        response_model=ExportResponse,
        responses={
            400: {"model": ErrorDetail},
            404: {"model": ErrorDetail},
        },
    )
    def export(
        project_id: str,
        body: ExportRequest,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> ExportResponse:
        project = load_project(registry, project_id)
        dest = Path(body.destination).expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            _do_export(project, body.format, dest)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=ErrorDetail(
                    code="export_failed",
                    message=str(exc),
                ).model_dump(),
            )
        if not dest.exists():
            raise HTTPException(
                status_code=400,
                detail=ErrorDetail(
                    code="export_failed",
                    message="Export completed but no file was produced",
                ).model_dump(),
            )
        return ExportResponse(
            path=str(dest),
            format=body.format,  # type: ignore[arg-type]
            size_bytes=dest.stat().st_size,
        )

    return router
