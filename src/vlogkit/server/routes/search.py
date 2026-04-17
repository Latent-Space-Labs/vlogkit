"""/projects/{id}/search: query + index."""
from __future__ import annotations

import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status

from vlogkit.project import Project
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import (
    ErrorDetail,
    IndexStatus,
    SearchHit,
    SearchResponse,
)


def _do_search(project: Project, query: str, k: int = 10) -> list[dict]:
    """Adapter — real call to vlogkit.search.

    Monkey-patchable in tests. Lazy-imports ``vlogkit.search`` so this
    route module can load even without the ``[search]`` extras installed.
    """
    from vlogkit.search.query import search_clips

    results = search_clips(query, project, n_results=k)
    return [_hit_to_dict(r) for r in results]


def _do_index(project: Project) -> None:
    """Adapter — build/refresh the semantic index. Lazy import."""
    from vlogkit.search.indexer import index_clips

    index_clips(project)


def _do_stats(project: Project) -> dict:
    """Adapter — return raw stats dict. Lazy import.

    ``get_search_stats`` returns ``None`` when search deps are not
    installed; we translate that into an ``ImportError`` so the caller
    can respond with 503 using the same code path as ``_do_search``.
    """
    from vlogkit.search.query import get_search_stats

    stats = get_search_stats(project)
    if stats is None:
        raise ImportError("sentrysearch not installed")
    return stats


def _hit_to_dict(r) -> dict:
    """Normalize a single search result to the ``SearchHit`` shape.

    ``search_clips`` returns dicts shaped like:
        {source_file, start_time, end_time, similarity_score}

    We map those to the API's ``SearchHit`` fields.
    """
    if isinstance(r, dict):
        # Real sentrysearch result — map field names.
        source_file = r.get("source_file") or r.get("clip_filename") or ""
        clip_filename = Path(source_file).name if source_file else r.get(
            "clip_filename", ""
        )
        return {
            "clip_filename": clip_filename,
            "clip_sha256": r.get("clip_sha256"),
            "chunk_start": float(
                r.get("start_time", r.get("chunk_start", 0.0)) or 0.0
            ),
            "chunk_end": float(
                r.get("end_time", r.get("chunk_end", 0.0)) or 0.0
            ),
            "score": float(
                r.get("similarity_score", r.get("score", 0.0)) or 0.0
            ),
            "snippet": r.get("snippet", "") or "",
        }
    # Fallback for dataclass/model-shaped results.
    return {
        "clip_filename": getattr(r, "clip_filename", ""),
        "clip_sha256": getattr(r, "clip_sha256", None),
        "chunk_start": float(getattr(r, "chunk_start", 0.0) or 0.0),
        "chunk_end": float(getattr(r, "chunk_end", 0.0) or 0.0),
        "score": float(getattr(r, "score", 0.0) or 0.0),
        "snippet": getattr(r, "snippet", "") or "",
    }


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["search"],
        dependencies=[Depends(require_token)],
    )

    @router.get(
        "/search",
        response_model=SearchResponse,
        responses={
            404: {"model": ErrorDetail},
            503: {"model": ErrorDetail},
        },
    )
    def search(
        project_id: str,
        q: str = Query(..., min_length=1),
        k: int = Query(10, ge=1, le=50),
        registry: ProjectRegistry = Depends(get_registry),
    ) -> SearchResponse:
        project = load_project(registry, project_id)
        try:
            hits = _do_search(project, q, k=k)
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail=ErrorDetail(
                    code="search_extras_not_installed",
                    message="Install optional deps: pip install -e '.[search]'",
                ).model_dump(),
            )
        return SearchResponse(
            query=q, hits=[SearchHit(**h) for h in hits]
        )

    @router.get(
        "/search/index",
        response_model=IndexStatus,
        responses={
            404: {"model": ErrorDetail},
            503: {"model": ErrorDetail},
        },
    )
    def get_index_status(
        project_id: str,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> IndexStatus:
        project = load_project(registry, project_id)
        try:
            stats = _do_stats(project)
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail=ErrorDetail(
                    code="search_extras_not_installed",
                    message="Install optional deps: pip install -e '.[search]'",
                ).model_dump(),
            )
        # sentrysearch stats use total_chunks / unique_source_files.
        indexed = stats.get(
            "indexed", stats.get("unique_source_files", 0)
        )
        total_clips = len(project.scan_clips())
        total = stats.get("total", total_clips)
        return IndexStatus(
            indexed=indexed,
            total=total,
            ready=indexed >= total and total > 0,
        )

    @router.post(
        "/search/index",
        status_code=status.HTTP_202_ACCEPTED,
        responses={404: {"model": ErrorDetail}},
    )
    def start_index(
        project_id: str,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> dict[str, str]:
        project = load_project(registry, project_id)
        job_id = uuid.uuid4().hex

        def run():
            try:
                _do_index(project)
            except Exception as exc:
                print(f"[index] job {job_id} failed: {exc}", flush=True)

        threading.Thread(target=run, daemon=True).start()
        return {"job_id": job_id}

    return router
