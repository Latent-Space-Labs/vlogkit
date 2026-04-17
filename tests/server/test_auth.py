"""Tests for bearer-token auth enforcement."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_upload_rejects_missing_authorization(client: TestClient) -> None:
    resp = client.post(
        "/upload",
        files={"file": ("clip.mp4", b"bytes", "video/mp4")},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing_bearer_token"


def test_upload_rejects_non_bearer_scheme(client: TestClient) -> None:
    resp = client.post(
        "/upload",
        headers={"Authorization": "Basic " + "x" * 16},
        files={"file": ("clip.mp4", b"bytes", "video/mp4")},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing_bearer_token"


def test_upload_rejects_wrong_token(client: TestClient) -> None:
    resp = client.post(
        "/upload",
        headers={"Authorization": "Bearer the-wrong-one"},
        files={"file": ("clip.mp4", b"bytes", "video/mp4")},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid_token"


def test_upload_accepts_correct_token(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/upload",
        headers=auth_headers,
        files={"file": ("clip.mp4", b"bytes", "video/mp4")},
    )
    assert resp.status_code == 200
