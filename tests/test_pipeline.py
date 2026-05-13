"""Unit tests for the analysis pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from vlogkit.analyze.pipeline import analyze_clip
from vlogkit.config import Settings
from vlogkit.models import ClipMetadata, SceneSegment


@pytest.fixture
def settings() -> Settings:
    return Settings(anthropic_api_key="test-key")


@pytest.fixture
def stub_metadata_and_transcribe(monkeypatch):
    """Stub metadata extraction + transcription so tests don't need a real video file."""

    def fake_extract(clip_path: Path) -> ClipMetadata:
        return ClipMetadata(
            filename=clip_path.name,
            path=clip_path,
            duration=10.0,
            resolution=(1920, 1080),
            fps=30.0,
            file_size=1024,
        )

    monkeypatch.setattr("vlogkit.analyze.pipeline.extract_metadata", fake_extract)
    monkeypatch.setattr("vlogkit.analyze.pipeline.transcribe_clip", lambda *a, **k: [])


def test_analyze_clip_populates_scenes(settings, stub_metadata_and_transcribe, tmp_path, monkeypatch):
    """Detected scenes must be attached to the returned ClipAnalysis."""
    fake_scenes = [
        SceneSegment(start=0.0, end=5.0),
        SceneSegment(start=5.0, end=10.0),
    ]
    monkeypatch.setattr("vlogkit.analyze.pipeline.detect_scenes", lambda p: fake_scenes)
    # Stub vision so this test focuses on scene detection only
    monkeypatch.setattr("vlogkit.analyze.pipeline.extract_keyframe", lambda *a, **k: tmp_path / "kf.jpg")
    monkeypatch.setattr("vlogkit.analyze.pipeline.describe_keyframe", lambda *a, **k: ("", []))

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not-a-real-mp4")

    result = analyze_clip(clip, settings, with_vision=False, keyframes_dir=tmp_path)

    assert len(result.scenes) == 2
    assert result.scenes[0].start == 0.0
    assert result.scenes[0].end == 5.0
    assert result.scenes[1].start == 5.0
    assert result.scenes[1].end == 10.0
