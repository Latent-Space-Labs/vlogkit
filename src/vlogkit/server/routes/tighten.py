"""/projects/{id}/tighten."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from vlogkit.models import Storyboard
from vlogkit.project import Project
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail, TightenRequest, TightenResponse


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


def _do_tighten(project: Project, dry_run: bool) -> TightenResponse:
    """Run the silence/filler auto-cut. Persists unless dry_run.

    Module-level so tests can monkeypatch it; tightening is pure-Python so
    tests run it for real.
    """
    from vlogkit.edit.tighten import load_tighten_config, tighten_storyboard

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

    config = load_tighten_config(project.root)
    tightened, stats = tighten_storyboard(sb, analyses, config)

    if not dry_run:
        from vlogkit.interactive.markdown import storyboard_to_markdown

        project.save_storyboard(tightened)
        project.storyboard_path().write_text(storyboard_to_markdown(tightened))

    return TightenResponse(
        original_duration=stats.original_duration,
        tightened_duration=stats.tightened_duration,
        removed_duration=stats.removed_duration,
        segments_before=stats.segments_before,
        segments_after=stats.segments_after,
        saved=(not dry_run),
    )


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["tighten"],
        dependencies=[Depends(require_token)],
    )

    @router.post(
        "/tighten",
        response_model=TightenResponse,
        responses={
            400: {"model": ErrorDetail},
            404: {"model": ErrorDetail},
        },
    )
    def tighten(
        project_id: str,
        body: TightenRequest,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> TightenResponse:
        project = load_project(registry, project_id)
        return _do_tighten(project, body.dry_run)

    return router
