"""Regression tests for the upload endpoint (ported from legacy server.py)."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_upload_writes_file_and_returns_hash(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_video_bytes: bytes,
    sample_video_sha256: str,
    tmp_project,
) -> None:
    resp = client.post(
        "/upload",
        headers={**auth_headers, "X-SHA256": sample_video_sha256},
        files={"file": ("clip.mp4", sample_video_bytes, "video/mp4")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sha256"] == sample_video_sha256
    assert body["size"] == len(sample_video_bytes)
    assert (tmp_project.root / body["filename"]).read_bytes() == sample_video_bytes


def test_upload_rejects_hash_mismatch(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_video_bytes: bytes,
) -> None:
    resp = client.post(
        "/upload",
        headers={**auth_headers, "X-SHA256": "0" * 64},
        files={"file": ("clip.mp4", sample_video_bytes, "video/mp4")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "hash_mismatch"


def test_upload_disambiguates_filenames(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_video_bytes: bytes,
    sample_video_sha256: str,
    tmp_project,
) -> None:
    for _ in range(2):
        resp = client.post(
            "/upload",
            headers={**auth_headers, "X-SHA256": sample_video_sha256},
            files={"file": ("clip.mp4", sample_video_bytes, "video/mp4")},
        )
        assert resp.status_code == 200

    files = sorted(p.name for p in tmp_project.root.iterdir() if p.is_file())
    assert files == ["clip.mp4", "clip_1.mp4"]
