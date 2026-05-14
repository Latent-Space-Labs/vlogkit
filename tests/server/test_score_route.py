"""Tests for POST /projects/{id}/score."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient


def _make_client(tmp_path: Path) -> tuple[TestClient, str]:
    """Build a test client for the desktop server with a one-project registry."""
    from vlogkit.server.app import create_desktop_app

    project_root = tmp_path / "p"
    project_root.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            [
                {
                    "id": "p",
                    "path": str(project_root),
                    "name": "p",
                    "last_opened": time.time(),
                }
            ]
        )
    )

    token = "test-token"
    app = create_desktop_app(registry_path=registry, token=token)
    return TestClient(app), token


def test_score_route_calls_run_scoring(tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_scoring(project, force=False):
        captured["project_root"] = project.root
        captured["force"] = force
        return 7

    monkeypatch.setattr("vlogkit.score.scorer.run_scoring", fake_run_scoring)

    client, token = _make_client(tmp_path)
    resp = client.post(
        "/projects/p/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"scored": 7}
    assert captured["force"] is False


def test_score_route_force_query_param(tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_scoring(project, force=False):
        captured["force"] = force
        return 0

    monkeypatch.setattr("vlogkit.score.scorer.run_scoring", fake_run_scoring)

    client, token = _make_client(tmp_path)
    resp = client.post(
        "/projects/p/score?force=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert captured["force"] is True


def test_score_route_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setattr("vlogkit.score.scorer.run_scoring", lambda **kw: 0)
    client, _token = _make_client(tmp_path)
    resp = client.post("/projects/p/score")
    assert resp.status_code in (401, 403)


def test_score_route_unknown_project_returns_404(tmp_path, monkeypatch):
    client, token = _make_client(tmp_path)
    resp = client.post(
        "/projects/nonexistent/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
