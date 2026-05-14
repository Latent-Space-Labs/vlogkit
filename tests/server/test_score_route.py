"""Tests for POST /projects/{id}/score (async + threaded)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _make_client(tmp_path: Path) -> tuple[TestClient, str]:
    """Build a test client for the desktop server with a one-project registry."""
    from vlogkit.server.app import create_desktop_app

    project_root = tmp_path / "p"
    project_root.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([
        {"id": "p", "path": str(project_root), "name": "p", "last_opened": 0}
    ]))

    token = "test-token"
    app = create_desktop_app(registry_path=registry, token=token)
    return TestClient(app), token


def test_score_route_returns_job_id_with_202(tmp_path, monkeypatch):
    """Endpoint should be async — return 202 with {job_id} immediately."""
    monkeypatch.setattr(
        "vlogkit.server.jobs.run_score_job",
        lambda **kw: None,
    )

    client, token = _make_client(tmp_path)
    resp = client.post(
        "/projects/p/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str) and len(body["job_id"]) > 0


def test_score_route_force_query_param_propagates(tmp_path, monkeypatch):
    """?force=true must reach run_score_job."""
    captured: dict[str, object] = {}

    async def fake_run_score_job(broker, project_id, project, job_id, force=False):
        captured["force"] = force

    monkeypatch.setattr("vlogkit.server.jobs.run_score_job", fake_run_score_job)

    client, token = _make_client(tmp_path)
    resp = client.post(
        "/projects/p/score?force=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202

    import time
    for _ in range(20):
        if "force" in captured:
            break
        time.sleep(0.05)
    assert captured.get("force") is True


def test_score_route_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setattr("vlogkit.server.jobs.run_score_job", lambda **kw: None)
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
