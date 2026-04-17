"""Tests for /media/{hash} accepting ?token= query param."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


FAKE = b"VIDEO" * 200


@pytest.fixture
def seeded(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> tuple[str, str]:
    folder = tmp_path / "vlog"
    folder.mkdir()
    (folder / "clip.mp4").write_bytes(FAKE)
    h = hashlib.sha256(FAKE).hexdigest()
    desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    )
    return h, h[:16]


def test_media_accepts_query_token(
    desktop_client: TestClient, test_token: str, seeded: tuple[str, str]
) -> None:
    h, _ = seeded
    resp = desktop_client.get(f"/media/{h}?token={test_token}")
    assert resp.status_code == 200
    assert resp.content == FAKE


def test_media_query_accepts_16_char_prefix(
    desktop_client: TestClient, test_token: str, seeded: tuple[str, str]
) -> None:
    _, short = seeded
    resp = desktop_client.get(f"/media/{short}?token={test_token}")
    assert resp.status_code == 200


def test_media_header_auth_still_works(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    seeded: tuple[str, str],
) -> None:
    h, _ = seeded
    resp = desktop_client.get(f"/media/{h}", headers=auth_headers)
    assert resp.status_code == 200


def test_media_rejects_wrong_query_token(
    desktop_client: TestClient, seeded: tuple[str, str]
) -> None:
    h, _ = seeded
    resp = desktop_client.get(f"/media/{h}?token=wrong")
    assert resp.status_code == 401
