"""Tests for the async score job + WS event emission."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def _make_project_with_scenes(tmp_path: Path):
    """Build a minimal Project with one cached clip having two scenes."""
    from vlogkit.config import Settings
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
    from vlogkit.project import Project

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path=clip, duration=10.0, resolution=(1, 1), fps=30.0, file_size=4
        ),
        scenes=[SceneSegment(start=0, end=5), SceneSegment(start=5, end=10)],
        file_hash="x",
    )
    project = Project(tmp_path, settings=Settings(anthropic_api_key="test-key", score_model="fake"))
    return project, clip, analysis


def test_run_score_job_publishes_started_progress_and_complete(tmp_path, monkeypatch):
    from vlogkit.models import MurchScore
    from vlogkit.project import Project
    from vlogkit.score import scorer as scorer_module
    from vlogkit.server import jobs as jobs_module
    from vlogkit.server.schemas import ScoreClipDone, ScoreComplete, ScoreProgress, ScoreStarted

    project, clip, analysis = _make_project_with_scenes(tmp_path)
    monkeypatch.setattr(Project, "scan_clips", lambda self: [clip])
    monkeypatch.setattr(Project, "load_analysis", lambda self, c: analysis)
    monkeypatch.setattr(Project, "save_analysis", lambda self, a: None)
    monkeypatch.setattr(scorer_module, "score_scene", lambda **kw: MurchScore(
        scene_type="narrative", aesthetic=50, credibility=50, impact=50,
        memorability=50, fun=50, composite=50.0,
    ))

    class FakeBackend:
        model = "fake"
        def complete(self, p, system=""):
            return ""
    monkeypatch.setattr("vlogkit.score.scorer.ClaudeBackend", lambda s: FakeBackend())

    published: list = []

    class FakeBroker:
        async def publish(self, project_id: str, event):
            published.append((project_id, event))

    asyncio.run(jobs_module.run_score_job(
        broker=FakeBroker(), project_id="p", project=project, job_id="j", force=False,
    ))

    types = [type(evt).__name__ for _pid, evt in published]
    assert types[0] == "ScoreStarted"
    assert "ScoreProgress" in types
    assert "ScoreClipDone" in types
    assert types[-1] == "ScoreComplete"
    assert sum(1 for t in types if t == "ScoreProgress") == 2


def test_run_score_job_publishes_failed_on_exception(tmp_path, monkeypatch):
    from vlogkit.project import Project
    from vlogkit.score import scorer as scorer_module
    from vlogkit.server import jobs as jobs_module
    from vlogkit.server.schemas import ScoreFailed

    project, clip, _analysis = _make_project_with_scenes(tmp_path)
    monkeypatch.setattr(Project, "scan_clips", lambda self: [clip])

    def boom(*a, **k):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(scorer_module, "run_scoring", boom)

    published: list = []

    class FakeBroker:
        async def publish(self, project_id, event):
            published.append((project_id, event))

    asyncio.run(jobs_module.run_score_job(
        broker=FakeBroker(), project_id="p", project=project, job_id="j", force=False,
    ))

    types = [type(evt).__name__ for _pid, evt in published]
    assert "ScoreFailed" in types
    failed = [evt for _pid, evt in published if isinstance(evt, ScoreFailed)][0]
    assert "simulated failure" in failed.error
