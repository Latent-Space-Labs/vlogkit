"""Verifies GET /projects/{id}/clips returns typed analysis.scenes[].murch."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _make_client_with_analyzed_project(tmp_path: Path):
    """Build a desktop server client; project has one clip with analysis cached, including a Murch score."""
    from vlogkit.config import Settings
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
    from vlogkit.project import Project, file_hash
    from vlogkit.server.app import create_desktop_app

    project_root = tmp_path / "p"
    project_root.mkdir()
    clip_file = project_root / "clip.mp4"
    clip_file.write_bytes(b"fake")

    project = Project(project_root, settings=Settings(anthropic_api_key="x"))
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path=clip_file, duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[
            SceneSegment(
                start=0, end=5, description="opening shot", tags=["sky"],
                murch=MurchScore(
                    scene_type="hook", aesthetic=80, credibility=70, impact=90,
                    memorability=85, fun=60, composite=82.0, rationale="strong",
                ),
            ),
            SceneSegment(start=5, end=10),  # unscored
        ],
        file_hash=file_hash(clip_file),
    )
    project.save_analysis(analysis)

    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([
        {"id": "p", "path": str(project_root), "name": "p", "last_opened": 0}
    ]))

    token = "test-token"
    app = create_desktop_app(registry_path=registry, token=token)
    return TestClient(app), token


def test_clips_route_returns_typed_scenes_with_murch(tmp_path):
    client, token = _make_client_with_analyzed_project(tmp_path)
    resp = client.get(
        "/projects/p/clips",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    clips = resp.json()
    assert len(clips) == 1
    clip = clips[0]
    assert clip["filename"] == "clip.mp4"
    assert clip["analysis"] is not None
    assert "scenes" in clip["analysis"]
    scenes = clip["analysis"]["scenes"]
    assert len(scenes) == 2

    # First scene has a murch score
    assert scenes[0]["murch"] is not None
    assert scenes[0]["murch"]["scene_type"] == "hook"
    assert scenes[0]["murch"]["composite"] == 82.0
    assert scenes[0]["description"] == "opening shot"
    assert scenes[0]["tags"] == ["sky"]

    # Second scene has no murch
    assert scenes[1]["murch"] is None
