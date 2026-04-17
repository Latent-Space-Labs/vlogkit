"""In-memory sha256 → Path index, keyed by project id.

Rebuilt when a project is registered. Uses chunked hashing so large clips
don't blow up RAM.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Lock

from vlogkit.project import Project


def _hash_file(path: Path, chunk: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for blk in iter(lambda: fh.read(chunk), b""):
            hasher.update(blk)
    return hasher.hexdigest()


class ClipIndex:
    """Maps sha256 (full or 16-char prefix) → absolute clip Path."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._by_project: dict[str, dict[str, Path]] = {}

    def add_project(self, project_id: str, project: Project) -> None:
        hashes: dict[str, Path] = {}
        for clip in project.scan_clips():
            try:
                h = _hash_file(clip)
            except OSError:
                continue  # skip unreadable
            hashes[h] = clip
        with self._lock:
            self._by_project[project_id] = hashes

    def remove_project(self, project_id: str) -> None:
        with self._lock:
            self._by_project.pop(project_id, None)

    def resolve(self, clip_hash: str) -> Path | None:
        """Look up by full 64-char hash OR 16-char prefix."""
        with self._lock:
            for hashes in self._by_project.values():
                if clip_hash in hashes:
                    return hashes[clip_hash]
                if len(clip_hash) == 16:
                    for full, path in hashes.items():
                        if full.startswith(clip_hash):
                            return path
        return None
