"""Tests for /projects/{id}/search."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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


def test_search_returns_hits(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vlogkit.server.routes import search as search_route

    def fake_search(project, query: str, k: int = 10):
        return [
            {
                "clip_filename": "a.mp4",
                "clip_sha256": "abc123def456" + "0" * 52,
                "chunk_start": 0.0,
                "chunk_end": 5.0,
                "score": 0.9,
                "snippet": "A bright sunset over the bridge",
            }
        ]

    monkeypatch.setattr(search_route, "_do_search", fake_search)

    resp = desktop_client.get(
        f"/projects/{registered}/search?q=sunset", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"] == "sunset"
    assert len(body["hits"]) == 1
    assert body["hits"][0]["clip_filename"] == "a.mp4"


def test_search_empty_query_returns_422(
    desktop_client: TestClient, auth_headers: dict[str, str], registered: str
) -> None:
    resp = desktop_client.get(
        f"/projects/{registered}/search?q=", headers=auth_headers
    )
    assert resp.status_code == 422


def test_search_unknown_project_returns_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.get(
        "/projects/deadbeefdeadbeef/search?q=anything",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_search_requires_auth(
    desktop_client: TestClient, registered: str
) -> None:
    resp = desktop_client.get(f"/projects/{registered}/search?q=x")
    assert resp.status_code == 401


def test_index_status_unknown_project_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.get(
        "/projects/deadbeefdeadbeef/search/index",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_post_index_starts_job(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vlogkit.server.routes import search as search_route

    def fake_build(project):
        pass

    monkeypatch.setattr(search_route, "_do_index", fake_build)

    resp = desktop_client.post(
        f"/projects/{registered}/search/index", headers=auth_headers
    )
    assert resp.status_code == 202
    assert "job_id" in resp.json()


def test_search_returns_503_when_deps_missing(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vlogkit.server.routes import search as search_route

    def fake_search(project, query: str, k: int = 10):
        raise ImportError("No module named 'sentrysearch'")

    monkeypatch.setattr(search_route, "_do_search", fake_search)

    resp = desktop_client.get(
        f"/projects/{registered}/search?q=x", headers=auth_headers
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "search_extras_not_installed"
