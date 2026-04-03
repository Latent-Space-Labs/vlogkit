"""Index video clips for semantic search using sentrysearch."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ..project import Project

console = Console()


def index_clips(project: Project, force: bool = False) -> int:
    """Index project clips for semantic video search.

    Chunks each clip, embeds via Gemini, and stores vectors in a
    per-project ChromaDB database.

    Args:
        project: The vlogkit project to index.
        force: If True, re-index all clips even if already indexed.

    Returns:
        Number of newly indexed clips.
    """
    from sentrysearch.chunker import chunk_video, is_still_frame_chunk, preprocess_chunk
    from sentrysearch.embedder import get_embedder, reset_embedder
    from sentrysearch.store import SentryStore

    settings = project.settings

    # Ensure Gemini API key is available to sentrysearch
    if settings.gemini_api_key:
        os.environ["GEMINI_API_KEY"] = settings.gemini_api_key
    elif not os.environ.get("GEMINI_API_KEY"):
        console.print(
            "[red]No Gemini API key configured.[/]\n"
            "Set VLOGKIT_GEMINI_API_KEY or GEMINI_API_KEY environment variable."
        )
        return 0

    db_path = settings.search_db_dir(project.root)
    store = SentryStore(db_path=db_path, backend="gemini")
    embedder = get_embedder("gemini")

    clips = project.scan_clips()
    if not clips:
        console.print("[yellow]No video clips found to index.[/]")
        return 0

    new_clips = 0
    new_chunks = 0
    skipped_still = 0

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Indexing clips for search...", total=len(clips))

            for clip in clips:
                abs_path = str(clip.resolve())
                basename = clip.name

                if not force and store.is_indexed(abs_path):
                    progress.update(task, advance=1, description=f"Skipping {basename} (indexed)")
                    continue

                progress.update(task, description=f"Chunking {basename}...")

                chunks = chunk_video(
                    abs_path,
                    chunk_duration=settings.search_chunk_duration,
                    overlap=settings.search_chunk_overlap,
                )

                embedded = []
                files_to_cleanup: list[str] = []

                for chunk in chunks:
                    chunk_path = chunk["chunk_path"]

                    if is_still_frame_chunk(chunk_path):
                        skipped_still += 1
                        files_to_cleanup.append(chunk_path)
                        continue

                    # Preprocess (downscale) for cheaper embedding
                    embed_path = preprocess_chunk(chunk_path)
                    if embed_path != chunk_path:
                        files_to_cleanup.append(embed_path)

                    embedding = embedder.embed_video_chunk(embed_path)
                    embedded.append({**chunk, "embedding": embedding})
                    files_to_cleanup.append(chunk_path)

                # Clean up temporary chunk files
                for f in files_to_cleanup:
                    try:
                        os.unlink(f)
                    except OSError:
                        pass

                # Clean up the temp directory
                if chunks:
                    tmp_dir = os.path.dirname(chunks[0]["chunk_path"])
                    shutil.rmtree(tmp_dir, ignore_errors=True)

                if embedded:
                    store.add_chunks(embedded)
                    new_clips += 1
                    new_chunks += len(embedded)

                progress.update(task, advance=1)

    finally:
        reset_embedder()

    # Summary
    stats = store.get_stats()
    still_msg = f", skipped {skipped_still} still-frame chunks" if skipped_still else ""
    console.print(
        f"[green]Indexed {new_chunks} chunks from {new_clips} new clips{still_msg}.[/]\n"
        f"Total index: {stats['total_chunks']} chunks from {stats['unique_source_files']} files."
    )

    return new_clips
