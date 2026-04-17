"""Tests for /analyze HTTP + WS event stream."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def registered_with_clips(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> tuple[str, Path]:
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "a.mp4").write_bytes(b"\x00" * 1024)
    entry = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()
    return entry["id"], folder


def test_post_analyze_starts_job_and_returns_id(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered_with_clips: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid, _ = registered_with_clips

    # Patch the job runner with a stub that emits two events then returns.
    from vlogkit.server import jobs

    async def fake_run(broker, project_id, project, job_id):
        from vlogkit.server.schemas import AnalyzeStarted, AnalyzeComplete
        await broker.publish(
            project_id, AnalyzeStarted(job_id=job_id, clip_count=1)
        )
        await broker.publish(
            project_id, AnalyzeComplete(job_id=job_id, duration_s=0.01)
        )

    monkeypatch.setattr(jobs, "run_analyze_job", fake_run)

    resp = desktop_client.post(
        f"/projects/{pid}/analyze", headers=auth_headers
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "job_id" in body


def test_analyze_unknown_project_returns_404(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    resp = desktop_client.post(
        "/projects/deadbeefdeadbeef/analyze", headers=auth_headers
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "project_not_found"


def test_analyze_requires_auth(
    desktop_client: TestClient,
    registered_with_clips: tuple[str, Path],
) -> None:
    pid, _ = registered_with_clips
    resp = desktop_client.post(f"/projects/{pid}/analyze")
    assert resp.status_code == 401


def test_ws_receives_analyze_events(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    test_token: str,
    registered_with_clips: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid, _ = registered_with_clips

    from vlogkit.server import jobs

    async def fake_run(broker, project_id, project, job_id):
        from vlogkit.server.schemas import AnalyzeStarted, AnalyzeComplete
        await broker.publish(
            project_id, AnalyzeStarted(job_id=job_id, clip_count=1)
        )
        await asyncio.sleep(0.01)
        await broker.publish(
            project_id, AnalyzeComplete(job_id=job_id, duration_s=0.02)
        )

    monkeypatch.setattr(jobs, "run_analyze_job", fake_run)

    with desktop_client.websocket_connect(
        f"/projects/{pid}/events?token={test_token}"
    ) as ws:
        desktop_client.post(f"/projects/{pid}/analyze", headers=auth_headers)

        events = []
        while True:
            msg = ws.receive_text()
            evt = json.loads(msg)
            events.append(evt)
            if evt["type"] == "analyze.complete":
                break

    types = [e["type"] for e in events]
    assert "analyze.started" in types
    assert "analyze.complete" in types


def test_ws_rejects_bad_token(
    desktop_client: TestClient,
    registered_with_clips: tuple[str, Path],
) -> None:
    pid, _ = registered_with_clips
    from fastapi import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with desktop_client.websocket_connect(
            f"/projects/{pid}/events?token=wrong-token"
        ):
            pass
