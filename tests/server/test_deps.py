"""Tests for shared dependency helpers."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from vlogkit.server.deps import load_project
from vlogkit.server.registry import ProjectRegistry


def test_load_project_returns_project(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    reg = ProjectRegistry(tmp_path / "projects.json")
    entry = reg.register(folder)
    project = load_project(reg, entry.id)
    assert project.root == folder


def test_load_project_raises_404_for_unknown(tmp_path: Path) -> None:
    reg = ProjectRegistry(tmp_path / "projects.json")
    with pytest.raises(HTTPException) as ei:
        load_project(reg, "not-a-real-id")
    assert ei.value.status_code == 404
    assert ei.value.detail["code"] == "project_not_found"
