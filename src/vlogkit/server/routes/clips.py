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


def create_media_router() -> APIRouter:
    router = APIRouter(
        tags=["media"],
        dependencies=[Depends(require_token)],
    )

    @router.get("/media/{clip_hash}")
    def stream_media(
        request: Request,
        clip_hash: str,
        registry: ProjectRegistry = Depends(_registry),
    ):
        from vlogkit.server.media import stream_file
        # FIXME(plan-3): replace linear scan with sha256→path index built during analyze
        # Search across all registered projects — the hash is globally unique.
        import hashlib
        for entry in registry.list():
            project = Project(root=Path(entry.path))
            for c in project.scan_clips():
                hasher = hashlib.sha256()
                with c.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        hasher.update(chunk)
                h_full = hasher.hexdigest()
                # Accept both 16-char prefix (current ClipSummary.sha256 shape) and 64-char full.
                if clip_hash in (h_full, h_full[:16]):
                    return stream_file(request, c)
        raise HTTPException(status_code=404, detail="media_not_found")

    return router
