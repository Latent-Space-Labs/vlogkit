"""Tests for the ClipIndex (sha256 → path)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from vlogkit.project import Project
from vlogkit.server.clip_index import ClipIndex


@pytest.fixture
def project_with_clips(tmp_path: Path) -> tuple[Project, dict[str, Path]]:
    root = tmp_path / "proj"
    root.mkdir()
    clips: dict[str, Path] = {}
    for name, body in [("a.mp4", b"A" * 1024), ("b.mov", b"B" * 512)]:
        path = root / name
        path.write_bytes(body)
        clips[hashlib.sha256(body).hexdigest()] = path
    return Project(root=root), clips


def test_index_resolves_full_sha256(
    project_with_clips: tuple[Project, dict[str, Path]]
) -> None:
    project, clips = project_with_clips
    idx = ClipIndex()
    idx.add_project("p1", project)
    for full_hash, path in clips.items():
        assert idx.resolve(full_hash) == path


def test_index_resolves_16_char_prefix(
    project_with_clips: tuple[Project, dict[str, Path]]
) -> None:
    project, clips = project_with_clips
    idx = ClipIndex()
    idx.add_project("p1", project)
    for full_hash, path in clips.items():
        assert idx.resolve(full_hash[:16]) == path


def test_index_returns_none_for_unknown(
    project_with_clips: tuple[Project, dict[str, Path]]
) -> None:
    project, _ = project_with_clips
    idx = ClipIndex()
    idx.add_project("p1", project)
    assert idx.resolve("0" * 64) is None
    assert idx.resolve("0" * 16) is None


def test_remove_project_drops_hashes(
    project_with_clips: tuple[Project, dict[str, Path]]
) -> None:
    project, clips = project_with_clips
    idx = ClipIndex()
    idx.add_project("p1", project)
    idx.remove_project("p1")
    for full_hash in clips:
        assert idx.resolve(full_hash) is None


def test_index_uses_chunked_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Large files must not be read_bytes()'d into memory."""
    root = tmp_path / "big"
    root.mkdir()
    big = root / "big.mp4"
    big.write_bytes(b"X" * (5 * 1024 * 1024))

    original_read_bytes = Path.read_bytes
    called_with_big = []

    def guarded(self: Path, *args, **kwargs):
        if self == big:
            called_with_big.append(self)
        return original_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guarded)

    idx = ClipIndex()
    idx.add_project("p1", Project(root=root))
    assert called_with_big == [], (
        "ClipIndex must use chunked hashing, not Path.read_bytes()"
    )
