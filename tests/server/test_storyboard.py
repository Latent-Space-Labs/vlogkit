"""Tests for /projects/{id}/storyboard."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _minimal_storyboard_body(clip_path: str) -> dict:
    """Build a minimal valid Storyboard dict for PUT requests.

    All fields of ``vlogkit.models.Storyboard`` have defaults, but we
    populate a realistic section/segment so the roundtrip assertion is
    meaningful.
    """
    return {
        "title": "Test Vlog",
        "sections": [
            {
                "title": "Intro",
                "segments": [
                    {
                        "clip_path": clip_path,
                        "in_point": 0.0,
                        "out_point": 2.5,
                        "label": "opening shot",
                        "transition": "",
                        "include": True,
                    }
                ],
                "notes": "",
            }
        ],
        "total_duration": 2.5,
        "llm_rationale": "",
    }


@pytest.fixture
def registered(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> str:
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "a.mp4").write_bytes(b"\x00" * 64)
    entry = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()
    return entry["id"]


@pytest.fixture
def clip_path(tmp_path: Path) -> str:
    return str(tmp_path / "proj" / "a.mp4")


def test_get_storyboard_empty_before_generation(
    desktop_client: TestClient, auth_headers: dict[str, str], registered: str
) -> None:
    resp = desktop_client.get(
        f"/projects/{registered}/storyboard", headers=auth_headers
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "storyboard_not_found"


def test_put_storyboard_roundtrips(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    clip_path: str,
) -> None:
    body = _minimal_storyboard_body(clip_path)

    resp = desktop_client.put(
        f"/projects/{registered}/storyboard",
        headers=auth_headers,
        json=body,
    )
    assert resp.status_code == 200, resp.text
    got = desktop_client.get(
        f"/projects/{registered}/storyboard", headers=auth_headers
    ).json()
    assert got["title"] == body["title"]
    assert len(got["sections"]) == len(body["sections"])
    assert got["sections"][0]["segments"][0]["label"] == "opening shot"


def test_put_storyboard_unknown_project_404(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    clip_path: str,
) -> None:
    body = _minimal_storyboard_body(clip_path)
    resp = desktop_client.put(
        "/projects/deadbeefdeadbeef/storyboard",
        headers=auth_headers,
        json=body,
    )
    assert resp.status_code == 404


def test_storyboard_requires_auth(
    desktop_client: TestClient, registered: str
) -> None:
    assert (
        desktop_client.get(f"/projects/{registered}/storyboard").status_code
        == 401
    )
    # PUT without auth — pass an empty dict so auth runs before body
    # validation returns a 422.
    assert (
        desktop_client.put(
            f"/projects/{registered}/storyboard", json={}
        ).status_code
        == 401
    )
