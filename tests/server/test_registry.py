"""Tests for the JSON-backed ProjectRegistry."""
from __future__ import annotations

from pathlib import Path

import pytest

from vlogkit.server.registry import ProjectRegistry


def test_project_id_is_stable_for_same_path(
    registry_path: Path, tmp_path: Path
) -> None:
    reg_a = ProjectRegistry(registry_path)
    reg_b = ProjectRegistry(registry_path)
    folder = tmp_path / "vlog"
    folder.mkdir()
    id_a = reg_a.register(folder).id
    id_b = reg_b.register(folder).id
    assert id_a == id_b


def test_register_is_idempotent(registry_path: Path, tmp_path: Path) -> None:
    reg = ProjectRegistry(registry_path)
    folder = tmp_path / "vlog"
    folder.mkdir()
    reg.register(folder)
    reg.register(folder)
    assert len(reg.list()) == 1


def test_list_returns_most_recent_first(
    registry_path: Path, tmp_path: Path
) -> None:
    reg = ProjectRegistry(registry_path)
    a = tmp_path / "a"
    a.mkdir()
    b = tmp_path / "b"
    b.mkdir()

    reg.register(a)
    reg.register(b)
    # Re-registering `a` should bump it to the top.
    reg.register(a)

    paths = [p.path for p in reg.list()]
    assert paths == [str(a), str(b)]


def test_forget_removes_entry_but_not_files(
    registry_path: Path, tmp_path: Path
) -> None:
    reg = ProjectRegistry(registry_path)
    folder = tmp_path / "vlog"
    folder.mkdir()
    (folder / "keep.mp4").write_bytes(b"data")

    entry = reg.register(folder)
    reg.forget(entry.id)

    assert reg.list() == []
    assert (folder / "keep.mp4").exists()


def test_get_by_id_returns_none_for_unknown(registry_path: Path) -> None:
    reg = ProjectRegistry(registry_path)
    assert reg.get("does-not-exist") is None


def test_persists_across_instances(
    registry_path: Path, tmp_path: Path
) -> None:
    folder = tmp_path / "vlog"
    folder.mkdir()
    ProjectRegistry(registry_path).register(folder)

    reg2 = ProjectRegistry(registry_path)
    assert len(reg2.list()) == 1
    assert reg2.list()[0].path == str(folder)


def test_register_requires_existing_directory(
    registry_path: Path, tmp_path: Path
) -> None:
    reg = ProjectRegistry(registry_path)
    with pytest.raises(FileNotFoundError):
        reg.register(tmp_path / "does-not-exist")
