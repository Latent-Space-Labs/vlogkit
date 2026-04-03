"""Search indexed video clips with natural language queries."""

from __future__ import annotations

import os

from ..project import Project


def search_clips(
    query: str,
    project: Project,
    n_results: int = 5,
) -> list[dict]:
    """Search indexed footage with a natural language query.

    Args:
        query: Natural language search string.
        project: The vlogkit project to search.
        n_results: Maximum number of results.

    Returns:
        List of result dicts sorted by relevance (best first).
        Each dict: {source_file, start_time, end_time, similarity_score}.
    """
    from sentrysearch.embedder import get_embedder, reset_embedder
    from sentrysearch.search import search_footage
    from sentrysearch.store import SentryStore

    settings = project.settings

    # Ensure Gemini API key is available
    if settings.gemini_api_key:
        os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

    db_path = settings.search_db_dir(project.root)
    store = SentryStore(db_path=db_path, backend="gemini")

    if store.get_stats()["total_chunks"] == 0:
        return []

    try:
        get_embedder("gemini")
        return search_footage(query, store, n_results=n_results)
    finally:
        reset_embedder()


def get_search_stats(project: Project) -> dict | None:
    """Return search index stats, or None if search deps not installed.

    Returns:
        Dict with total_chunks, unique_source_files, source_files keys,
        or None if sentrysearch is not available.
    """
    try:
        from sentrysearch.store import SentryStore
    except ImportError:
        return None

    db_path = project.settings.search_db_dir(project.root)
    if not db_path.exists():
        return {"total_chunks": 0, "unique_source_files": 0, "source_files": []}

    store = SentryStore(db_path=db_path, backend="gemini")
    return store.get_stats()
