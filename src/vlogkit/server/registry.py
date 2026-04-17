"""Persistent registry of recent vlogkit projects, keyed by folder path hash."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectEntry:
    id: str
    path: str
    name: str
    last_opened: float  # Unix epoch seconds


class ProjectRegistry:
    """JSON-backed list of recent projects.

    Not thread-safe — the server is single-process and calls are serialized
    by asyncio. If concurrency becomes an issue later, add a lock.
    """

    def __init__(self, storage_path: Path) -> None:
        self._path = storage_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _compute_id(folder: Path) -> str:
        # Stable identifier across registry recreations — hash the absolute path.
        return hashlib.sha256(str(folder.resolve()).encode()).hexdigest()[:16]

    def _load(self) -> list[ProjectEntry]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text())
        except json.JSONDecodeError:
            return []
        return [ProjectEntry(**item) for item in raw]

    def _save(self, entries: list[ProjectEntry]) -> None:
        self._path.write_text(
            json.dumps([asdict(e) for e in entries], indent=2)
        )

    def register(self, folder: Path) -> ProjectEntry:
        if not folder.is_dir():
            raise FileNotFoundError(f"not a directory: {folder}")
        entry = ProjectEntry(
            id=self._compute_id(folder),
            path=str(folder.resolve()),
            name=folder.name,
            last_opened=time.time(),
        )
        entries = [e for e in self._load() if e.id != entry.id]
        entries.insert(0, entry)
        self._save(entries)
        return entry

    def list(self) -> list[ProjectEntry]:
        return sorted(self._load(), key=lambda e: e.last_opened, reverse=True)

    def get(self, project_id: str) -> ProjectEntry | None:
        for e in self._load():
            if e.id == project_id:
                return e
        return None

    def forget(self, project_id: str) -> bool:
        entries = self._load()
        remaining = [e for e in entries if e.id != project_id]
        if len(remaining) == len(entries):
            return False
        self._save(remaining)
        return True
