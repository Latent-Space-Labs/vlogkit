"""Tests for /projects/{id}/tighten."""
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


def _segment_count(folder: Path) -> int:
    from vlogkit.project import Project

    sb = Project(folder).load_storyboard()
    assert sb is not None
    return sum(len(sec.segments) for sec in sb.sections)


@pytest.fixture(autouse=True)
def _mount_tighten_router(desktop_client: TestClient) -> None:
    """Mount the tighten router (app.py wiring is owned by the integrator)."""
    from vlogkit.server.routes import tighten as tighten_route

    if not any(
        getattr(r, "path", "") == "/projects/{project_id}/tighten"
        for r in desktop_client.app.routes
    ):
        desktop_client.app.include_router(tighten_route.create_router())


@pytest.fixture
def registered(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> tuple[str, Path]:
    folder = tmp_path / "proj"
    folder.mkdir()
    _seed(folder)
    entry = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()
    return entry["id"], folder


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


def test_tighten_dry_run_does_not_save(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: tuple[str, Path],
) -> None:
    project_id, folder = registered
    before = _segment_count(folder)
    resp = desktop_client.post(
        f"/projects/{project_id}/tighten",
        headers=auth_headers,
        json={"dry_run": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["saved"] is False
    assert body["segments_before"] >= 1
    assert set(body) == {
        "original_duration",
        "tightened_duration",
        "removed_duration",
        "segments_before",
        "segments_after",
        "saved",
    }
    # storyboard on disk is unchanged
    assert _segment_count(folder) == before


def test_tighten_apply_saves_split_storyboard(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: tuple[str, Path],
) -> None:
    project_id, folder = registered
    before = _segment_count(folder)
    resp = desktop_client.post(
        f"/projects/{project_id}/tighten",
        headers=auth_headers,
        json={"dry_run": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["saved"] is True
    # cutting "um" splits the single segment into more segments
    assert body["segments_after"] > body["segments_before"]
    assert _segment_count(folder) > before
    # markdown sidecar got rewritten too
    from vlogkit.project import Project

    assert Project(folder).storyboard_path().exists()


def test_tighten_unknown_project_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.post(
        "/projects/deadbeefdeadbeef/tighten",
        headers=auth_headers,
        json={"dry_run": True},
    )
    assert resp.status_code == 404


def test_tighten_requires_auth(
    desktop_client: TestClient, registered: tuple[str, Path]
) -> None:
    project_id, _ = registered
    resp = desktop_client.post(
        f"/projects/{project_id}/tighten",
        json={"dry_run": True},
    )
    assert resp.status_code == 401


def test_tighten_no_storyboard_returns_400(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered_bare: str,
) -> None:
    resp = desktop_client.post(
        f"/projects/{registered_bare}/tighten",
        headers=auth_headers,
        json={"dry_run": True},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "no_storyboard"
