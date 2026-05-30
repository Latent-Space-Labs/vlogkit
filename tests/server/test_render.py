"""Tests for POST /projects/{id}/render (async + threaded) and run_render_job."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient


def _make_client(tmp_path: Path) -> tuple[TestClient, str]:
    """Build a test client for the desktop server with a one-project registry."""
    from vlogkit.server.app import create_desktop_app

    project_root = tmp_path / "p"
    project_root.mkdir(exist_ok=True)
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([
        {"id": "p", "path": str(project_root), "name": "p", "last_opened": 0}
    ]))

    token = "test-token"
    app = create_desktop_app(registry_path=registry, token=token)
    return TestClient(app), token


def _seed_storyboard(project_root: Path) -> None:
    """Write a minimal storyboard JSON cache with one included segment."""
    from vlogkit.config import Settings
    from vlogkit.models import (
        Storyboard,
        StoryboardSection,
        StoryboardSegment,
    )
    from vlogkit.project import Project

    project_root.mkdir(parents=True, exist_ok=True)
    clip = project_root / "clip.mp4"
    clip.write_bytes(b"fake")
    sb = Storyboard(
        title="t",
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    StoryboardSegment(
                        clip_path=clip,
                        in_point=0.0,
                        out_point=5.0,
                        include=True,
                    )
                ],
            )
        ],
    )
    project = Project(project_root, settings=Settings())
    project.save_storyboard(sb)


# ---- Route tests ------------------------------------------------------------


def test_render_route_returns_job_id_with_202(tmp_path, monkeypatch):
    """Endpoint should be async — return 202 with {job_id} immediately."""
    async def fake_run_render_job(*a, **k):
        return None

    monkeypatch.setattr(
        "vlogkit.server.jobs.run_render_job", fake_run_render_job
    )

    client, token = _make_client(tmp_path)
    resp = client.post(
        "/projects/p/render",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str) and len(body["job_id"]) > 0


def test_render_route_body_propagates(tmp_path, monkeypatch):
    """Request body fields must reach run_render_job."""
    captured: dict[str, object] = {}

    async def fake_run_render_job(
        broker, project_id, project, job_id,
        captions=False, resolution=None, fps=None,
    ):
        captured["captions"] = captions
        captured["resolution"] = resolution
        captured["fps"] = fps

    monkeypatch.setattr(
        "vlogkit.server.jobs.run_render_job", fake_run_render_job
    )

    client, token = _make_client(tmp_path)
    resp = client.post(
        "/projects/p/render",
        headers={"Authorization": f"Bearer {token}"},
        json={"captions": True, "resolution": "720p", "fps": 24.0},
    )
    assert resp.status_code == 202

    for _ in range(40):
        if "captions" in captured:
            break
        time.sleep(0.05)
    assert captured.get("captions") is True
    assert captured.get("resolution") == "720p"
    assert captured.get("fps") == 24.0


def test_render_route_requires_auth(tmp_path, monkeypatch):
    async def fake_run_render_job(*a, **k):
        return None

    monkeypatch.setattr(
        "vlogkit.server.jobs.run_render_job", fake_run_render_job
    )
    client, _token = _make_client(tmp_path)
    resp = client.post("/projects/p/render", json={})
    assert resp.status_code in (401, 403)


def test_render_route_unknown_project_returns_404(tmp_path, monkeypatch):
    client, token = _make_client(tmp_path)
    resp = client.post(
        "/projects/nonexistent/render",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp.status_code == 404


# ---- Job tests --------------------------------------------------------------


def _make_project_with_storyboard(tmp_path: Path):
    from vlogkit.config import Settings
    from vlogkit.models import (
        Storyboard,
        StoryboardSection,
        StoryboardSegment,
    )
    from vlogkit.project import Project

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    sb = Storyboard(
        title="t",
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    StoryboardSegment(
                        clip_path=clip, in_point=0.0, out_point=5.0, include=True
                    )
                ],
            )
        ],
    )
    project = Project(tmp_path, settings=Settings())
    return project, sb


def test_run_render_job_publishes_started_and_complete(tmp_path, monkeypatch):
    from vlogkit.captions import render as render_module
    from vlogkit.project import Project
    from vlogkit.server import jobs as jobs_module

    project, sb = _make_project_with_storyboard(tmp_path)
    monkeypatch.setattr(Project, "load_storyboard", lambda self: sb)
    monkeypatch.setattr(Project, "load_all_analyses", lambda self: [])

    def fake_render(storyboard, output_path, **kw):
        Path(output_path).write_bytes(b"rendered-mp4-bytes")
        return Path(output_path)

    monkeypatch.setattr(render_module, "render", fake_render)

    published: list = []

    class FakeBroker:
        async def publish(self, project_id, event):
            published.append((project_id, event))

    asyncio.run(jobs_module.run_render_job(
        broker=FakeBroker(), project_id="p", project=project, job_id="j",
    ))

    types = [type(evt).__name__ for _pid, evt in published]
    assert types[0] == "RenderStarted"
    assert types[-1] == "RenderComplete"
    complete = published[-1][1]
    assert complete.output_path.endswith("render.mp4")
    assert complete.size_bytes == len(b"rendered-mp4-bytes")


def test_run_render_job_no_storyboard_publishes_failed(tmp_path, monkeypatch):
    from vlogkit.project import Project
    from vlogkit.server import jobs as jobs_module

    project, _sb = _make_project_with_storyboard(tmp_path)
    monkeypatch.setattr(Project, "load_storyboard", lambda self: None)
    # storyboard_path does not exist -> no markdown fallback

    published: list = []

    class FakeBroker:
        async def publish(self, project_id, event):
            published.append((project_id, event))

    asyncio.run(jobs_module.run_render_job(
        broker=FakeBroker(), project_id="p", project=project, job_id="j",
    ))

    types = [type(evt).__name__ for _pid, evt in published]
    assert "RenderFailed" in types
    assert all(t != "RenderComplete" for t in types)


def test_run_render_job_publishes_failed_on_exception(tmp_path, monkeypatch):
    from vlogkit.captions import render as render_module
    from vlogkit.project import Project
    from vlogkit.server import jobs as jobs_module
    from vlogkit.server.schemas import RenderFailed

    project, sb = _make_project_with_storyboard(tmp_path)
    monkeypatch.setattr(Project, "load_storyboard", lambda self: sb)
    monkeypatch.setattr(Project, "load_all_analyses", lambda self: [])

    def boom(*a, **k):
        raise RuntimeError("simulated render failure")

    monkeypatch.setattr(render_module, "render", boom)

    published: list = []

    class FakeBroker:
        async def publish(self, project_id, event):
            published.append((project_id, event))

    asyncio.run(jobs_module.run_render_job(
        broker=FakeBroker(), project_id="p", project=project, job_id="j",
    ))

    failed = [evt for _pid, evt in published if isinstance(evt, RenderFailed)]
    assert failed
    assert "simulated render failure" in failed[0].error


def test_run_render_job_captions_without_libass_fails(tmp_path, monkeypatch):
    from vlogkit.project import Project
    from vlogkit.server import jobs as jobs_module
    from vlogkit.server.schemas import RenderComplete, RenderFailed

    project, sb = _make_project_with_storyboard(tmp_path)
    monkeypatch.setattr(Project, "load_storyboard", lambda self: sb)
    monkeypatch.setattr(Project, "load_all_analyses", lambda self: [])
    monkeypatch.setattr(
        "vlogkit.ffmpeg_util.has_libass", lambda bin: False
    )

    published: list = []

    class FakeBroker:
        async def publish(self, project_id, event):
            published.append((project_id, event))

    asyncio.run(jobs_module.run_render_job(
        broker=FakeBroker(), project_id="p", project=project, job_id="j",
        captions=True,
    ))

    assert any(isinstance(e, RenderFailed) for _p, e in published)
    assert not any(isinstance(e, RenderComplete) for _p, e in published)


# ---- WebSocket integration --------------------------------------------------


def test_ws_receives_render_events(tmp_path, monkeypatch):
    from vlogkit.captions import render as render_module

    _seed_storyboard(tmp_path / "p")

    def fast_render(storyboard, output_path, **kw):
        Path(output_path).write_bytes(b"x")
        return Path(output_path)

    monkeypatch.setattr(render_module, "render", fast_render)

    client, token = _make_client(tmp_path)

    with client.websocket_connect(
        f"/projects/p/events?token={token}"
    ) as ws:
        client.post(
            "/projects/p/render",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        events = []
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            evt = json.loads(ws.receive_text())
            events.append(evt)
            if evt["type"] in ("render.complete", "render.failed"):
                break

    types = [e["type"] for e in events]
    assert "render.started" in types
    assert "render.complete" in types
