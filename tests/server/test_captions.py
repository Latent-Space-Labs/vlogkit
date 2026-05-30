"""Tests for /projects/{id}/captions."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _seed(folder: Path):
    from vlogkit.models import (
        ClipAnalysis,
        ClipMetadata,
        Storyboard,
        StoryboardSection,
        StoryboardSegment,
        TranscriptSegment,
        WordTimestamp,
    )
    from vlogkit.project import Project, file_hash

    clip = folder / "clip.mp4"
    clip.write_bytes(b"video-bytes")
    p = Project(folder)
    p.init()
    p.save_analysis(
        ClipAnalysis(
            metadata=ClipMetadata(
                filename="clip.mp4",
                path=clip.resolve(),
                duration=10.0,
                resolution=(1920, 1080),
                fps=30.0,
                file_size=clip.stat().st_size,
            ),
            transcript=[
                TranscriptSegment(
                    start=0,
                    end=2,
                    text="hello um world",
                    words=[
                        WordTimestamp(start=0.0, end=0.5, word="hello"),
                        WordTimestamp(start=0.6, end=0.9, word="um"),
                        WordTimestamp(start=1.0, end=2.0, word="world"),
                    ],
                )
            ],
            file_hash=file_hash(clip),
        )
    )
    p.save_storyboard(
        Storyboard(
            title="T",
            sections=[
                StoryboardSection(
                    title="s",
                    segments=[
                        StoryboardSegment(
                            clip_path=clip.resolve(),
                            in_point=0.0,
                            out_point=2.0,
                            include=True,
                        )
                    ],
                )
            ],
        )
    )


@pytest.fixture(autouse=True)
def _mount_captions_router(desktop_client: TestClient) -> None:
    """Mount the captions router (app.py wiring is owned by the integrator)."""
    from vlogkit.server.routes import captions as captions_route

    if not any(
        getattr(r, "path", "") == "/projects/{project_id}/captions"
        for r in desktop_client.app.routes
    ):
        desktop_client.app.include_router(captions_route.create_router())


@pytest.fixture
def registered(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> str:
    folder = tmp_path / "proj"
    folder.mkdir()
    _seed(folder)
    entry = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()
    return entry["id"]


@pytest.fixture
def registered_bare(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> str:
    from vlogkit.project import Project

    folder = tmp_path / "bare"
    folder.mkdir()
    Project(folder).init()
    entry = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()
    return entry["id"]


def test_captions_writes_file(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
) -> None:
    resp = desktop_client.post(
        f"/projects/{registered}/captions",
        headers=auth_headers,
        json={"format": "srt"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format"] == "srt"
    assert body["path"].endswith("captions.srt")
    assert body["size_bytes"] > 0
    assert body["cue_count"] >= 1
    assert Path(body["path"]).exists()


def test_captions_vtt_format(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
) -> None:
    resp = desktop_client.post(
        f"/projects/{registered}/captions",
        headers=auth_headers,
        json={"format": "vtt"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["format"] == "vtt"
    assert body["path"].endswith("captions.vtt")


def test_captions_unknown_project_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.post(
        "/projects/deadbeefdeadbeef/captions",
        headers=auth_headers,
        json={"format": "srt"},
    )
    assert resp.status_code == 404


def test_captions_requires_auth(
    desktop_client: TestClient, registered: str
) -> None:
    resp = desktop_client.post(
        f"/projects/{registered}/captions",
        json={"format": "srt"},
    )
    assert resp.status_code == 401


def test_captions_bad_format_returns_422(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
) -> None:
    resp = desktop_client.post(
        f"/projects/{registered}/captions",
        headers=auth_headers,
        json={"format": "invalid"},
    )
    assert resp.status_code == 422


def test_captions_no_storyboard_returns_400(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered_bare: str,
) -> None:
    resp = desktop_client.post(
        f"/projects/{registered_bare}/captions",
        headers=auth_headers,
        json={"format": "srt"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "no_storyboard"
