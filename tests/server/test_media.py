"""Tests for /media/{hash} range-aware streaming."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


FAKE_VIDEO = b"VIDEO" * 200  # 1000 bytes


@pytest.fixture
def seeded_project(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> tuple[str, str, Path]:
    folder = tmp_path / "vlog"
    folder.mkdir()
    clip = folder / "clip.mp4"
    clip.write_bytes(FAKE_VIDEO)
    clip_hash = hashlib.sha256(FAKE_VIDEO).hexdigest()
    entry = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()
    return entry["id"], clip_hash, clip


def test_media_returns_full_body_without_range(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project,
) -> None:
    _, clip_hash, _ = seeded_project
    resp = desktop_client.get(f"/media/{clip_hash}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content == FAKE_VIDEO
    assert resp.headers["content-type"] == "video/mp4"
    assert resp.headers["accept-ranges"] == "bytes"


def test_media_honors_range_header(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project,
) -> None:
    _, clip_hash, _ = seeded_project
    resp = desktop_client.get(
        f"/media/{clip_hash}",
        headers={**auth_headers, "Range": "bytes=10-19"},
    )
    assert resp.status_code == 206
    assert resp.content == FAKE_VIDEO[10:20]
    assert resp.headers["content-range"] == f"bytes 10-19/{len(FAKE_VIDEO)}"
    assert resp.headers["content-length"] == "10"


def test_media_open_ended_range(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project,
) -> None:
    _, clip_hash, _ = seeded_project
    resp = desktop_client.get(
        f"/media/{clip_hash}",
        headers={**auth_headers, "Range": "bytes=995-"},
    )
    assert resp.status_code == 206
    assert resp.content == FAKE_VIDEO[995:]


def test_media_unknown_hash_returns_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.get(
        f"/media/{'0' * 64}", headers=auth_headers
    )
    assert resp.status_code == 404


def test_media_requires_auth(
    desktop_client: TestClient, seeded_project
) -> None:
    _, clip_hash, _ = seeded_project
    resp = desktop_client.get(f"/media/{clip_hash}")
    assert resp.status_code == 401


def test_media_accepts_16_char_hash_prefix(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project,
) -> None:
    _, full_hash, _ = seeded_project
    short = full_hash[:16]
    resp = desktop_client.get(f"/media/{short}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content == FAKE_VIDEO
