"""/projects/{id}/clips endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from vlogkit.project import Project
from vlogkit.server.auth import require_token, require_token_or_query
from vlogkit.server.deps import get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ClipSummary, ErrorDetail


def _to_clip_analysis_summary(analysis):
    """Convert internal ClipAnalysis → ClipAnalysisSummary (the API-facing shape)."""
    from vlogkit.server.schemas import ClipAnalysisSummary, ClipMurchScore, ClipScene

    scenes = []
    for s in analysis.scenes:
        murch = None
        if s.murch is not None:
            murch = ClipMurchScore(
                scene_type=s.murch.scene_type,
                aesthetic=s.murch.aesthetic,
                credibility=s.murch.credibility,
                impact=s.murch.impact,
                memorability=s.murch.memorability,
                fun=s.murch.fun,
                composite=s.murch.composite,
                rationale=s.murch.rationale,
            )
        scenes.append(ClipScene(
            start=s.start, end=s.end,
            description=s.description, tags=list(s.tags),
            keyframe_path=str(s.keyframe_path) if s.keyframe_path else None,
            murch=murch,
        ))
    return ClipAnalysisSummary(scenes=scenes, summary=analysis.summary or "")


def _summarize_clip(project: Project, clip_path: Path) -> ClipSummary:
    cached = project.load_analysis(clip_path) if hasattr(
        project, "load_analysis"
    ) else None
    return ClipSummary(
        filename=clip_path.name,
        size=clip_path.stat().st_size,
        sha256=getattr(cached, "file_hash", None) if cached else None,
        status="analyzed" if cached else "unanalyzed",
        analysis=_to_clip_analysis_summary(cached) if cached else None,
    )


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["clips"],
        dependencies=[Depends(require_token)],
    )

    @router.get(
        "/clips",
        response_model=list[ClipSummary],
        responses={404: {"model": ErrorDetail}},
    )
    def list_clips(
        project_id: str,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> list[ClipSummary]:
        project = load_project(registry, project_id)
        clips = project.scan_clips()
        return [_summarize_clip(project, c) for c in clips]

    @router.get(
        "/clips/{clip_hash}",
        response_model=ClipSummary,
        responses={404: {"model": ErrorDetail}},
    )
    def get_clip(
        project_id: str,
        clip_hash: str,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> ClipSummary:
        project = load_project(registry, project_id)
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
        dependencies=[Depends(require_token_or_query)],
    )

    @router.get(
        "/media/{clip_hash}",
        responses={404: {"model": ErrorDetail}},
    )
    def stream_media(
        request: Request,
        clip_hash: str,
    ):
        from vlogkit.server.media import stream_file
        index = request.app.state.clip_index
        path = index.resolve(clip_hash)
        if path is None:
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    code="media_not_found",
                    message=f"No clip with hash {clip_hash} found in any registered project",
                ).model_dump(),
            )
        return stream_file(request, path)

    return router
