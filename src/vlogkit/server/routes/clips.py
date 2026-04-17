"""/projects/{id}/clips endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from vlogkit.project import Project
from vlogkit.server.auth import require_token
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ClipSummary, ErrorDetail


def _registry(request: Request) -> ProjectRegistry:
    return request.app.state.registry


def _load_project(registry: ProjectRegistry, project_id: str) -> Project:
    entry = registry.get(project_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="project_not_found",
                message=f"Unknown project: {project_id}",
            ).model_dump(),
        )
    return Project(root=Path(entry.path))


def _summarize_clip(project: Project, clip_path: Path) -> ClipSummary:
    cached = project.load_analysis(clip_path) if hasattr(
        project, "load_analysis"
    ) else None
    return ClipSummary(
        filename=clip_path.name,
        size=clip_path.stat().st_size,
        sha256=getattr(cached, "file_hash", None) if cached else None,
        status="analyzed" if cached else "unanalyzed",
        analysis=cached.model_dump(mode="json") if cached else None,
    )


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["clips"],
        dependencies=[Depends(require_token)],
    )

    @router.get("/clips", response_model=list[ClipSummary])
    def list_clips(
        project_id: str,
        registry: ProjectRegistry = Depends(_registry),
    ) -> list[ClipSummary]:
        project = _load_project(registry, project_id)
        clips = project.scan_clips()
        return [_summarize_clip(project, c) for c in clips]

    @router.get("/clips/{clip_hash}", response_model=ClipSummary)
    def get_clip(
        project_id: str,
        clip_hash: str,
        registry: ProjectRegistry = Depends(_registry),
    ) -> ClipSummary:
        project = _load_project(registry, project_id)
        for c in project.scan_clips():
            summary = _summarize_clip(project, c)
            if summary.sha256 == clip_hash:
                return summary
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="clip_not_found",
                message=f"No clip with hash {clip_hash} in project",
            ).model_dump(),
        )

    return router
