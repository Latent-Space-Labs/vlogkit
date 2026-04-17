"""Tests for /projects/{id}/clips endpoints."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def registered_project(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> tuple[str, Path]:
    folder = tmp_path / "vlog"
    folder.mkdir()
    # Create two fake video files so Project.scan_clips() sees them.
    (folder / "a.mp4").write_bytes(b"\x00" * 64)
    (folder / "b.mov").write_bytes(b"\x00" * 64)
    entry = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()
    return entry["id"], folder


def test_list_clips_returns_unanalyzed_clips(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered_project: tuple[str, Path],
) -> None:
    pid, _ = registered_project
    resp = desktop_client.get(
        f"/projects/{pid}/clips", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    names = sorted(c["filename"] for c in body)
    assert names == ["a.mp4", "b.mov"]
    for c in body:
        assert c["status"] == "unanalyzed"
        assert c["analysis"] is None


def test_list_clips_unknown_project_returns_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.get(
        "/projects/deadbeefdeadbeef/clips", headers=auth_headers
    )
    assert resp.status_code == 404


def test_get_clip_unknown_hash_returns_404(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered_project: tuple[str, Path],
) -> None:
    pid, _ = registered_project
    resp = desktop_client.get(
        f"/projects/{pid}/clips/{'0' * 64}", headers=auth_headers
    )
    assert resp.status_code == 404


def test_clips_route_requires_auth(
    desktop_client: TestClient, registered_project: tuple[str, Path]
) -> None:
    pid, _ = registered_project
    resp = desktop_client.get(f"/projects/{pid}/clips")
    assert resp.status_code == 401
