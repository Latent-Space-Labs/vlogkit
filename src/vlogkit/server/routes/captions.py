"""/projects/{id}/captions."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from vlogkit.models import Storyboard
from vlogkit.project import Project
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import CaptionsRequest, CaptionsResponse, ErrorDetail


def _load_storyboard(project: Project) -> Storyboard | None:
    """Load the cached storyboard, falling back to storyboard.md."""
    sb = project.load_storyboard()
    if sb is not None:
        return sb
    sb_path = project.storyboard_path()
    if sb_path.exists():
        from vlogkit.interactive.markdown import markdown_to_storyboard

        return markdown_to_storyboard(sb_path.read_text(), project_root=project.root)
    return None


def _do_captions(project: Project, fmt: str) -> tuple[Path, int]:
    """Build the caption sidecar file. Returns (path, cue_count).

    Module-level so tests can monkeypatch it; captions are pure-Python so
    tests run it for real.
    """
    from vlogkit.captions.cues import build_cues
    from vlogkit.captions.pipeline import generate_caption_file, load_caption_style

    sb = _load_storyboard(project)
    if sb is None:
        raise HTTPException(
            status_code=400,
            detail=ErrorDetail(
                code="no_storyboard",
                message="No storyboard found; run storyboard generation first.",
            ).model_dump(),
        )

    analyses = project.load_all_analyses()
    if not analyses:
        raise HTTPException(
            status_code=400,
            detail=ErrorDetail(
                code="no_analyses",
                message="No clip analyses found; run analyze first.",
            ).model_dump(),
        )

    style = load_caption_style(project.root)
    out = project.cache_dir / f"captions.{fmt}"
    generate_caption_file(sb, analyses, fmt=fmt, output_path=out, style=style)
    cue_count = len(build_cues(sb, analyses, style))
    return out, cue_count


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["captions"],
        dependencies=[Depends(require_token)],
    )

    @router.post(
        "/captions",
        response_model=CaptionsResponse,
        responses={
            400: {"model": ErrorDetail},
            404: {"model": ErrorDetail},
        },
    )
    def captions(
        project_id: str,
        body: CaptionsRequest,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> CaptionsResponse:
        project = load_project(registry, project_id)
        out, cue_count = _do_captions(project, body.format)
        return CaptionsResponse(
            path=str(out),
            format=body.format,  # type: ignore[arg-type]
            size_bytes=out.stat().st_size,
            cue_count=cue_count,
        )

    return router
