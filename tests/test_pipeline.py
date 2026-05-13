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


def test_analyze_clip_vision_populates_descriptions(settings, stub_metadata_and_transcribe, tmp_path, monkeypatch):
    """When with_vision=True, each scene gets a description, tags, and a keyframe path."""
    fake_scenes = [SceneSegment(start=0.0, end=5.0), SceneSegment(start=5.0, end=10.0)]
    monkeypatch.setattr("vlogkit.analyze.pipeline.detect_scenes", lambda p: fake_scenes)

    captured_keyframes: list[Path] = []

    def fake_extract_keyframe(clip_path: Path, timestamp: float, output_path: Path) -> Path:
        output_path.write_bytes(b"fake-jpg")
        captured_keyframes.append(output_path)
        return output_path

    def fake_describe(image_path: str, s: Settings) -> tuple[str, list[str]]:
        return (f"description for {Path(image_path).name}", ["tagA", "tagB"])

    monkeypatch.setattr("vlogkit.analyze.pipeline.extract_keyframe", fake_extract_keyframe)
    monkeypatch.setattr("vlogkit.analyze.pipeline.describe_keyframe", fake_describe)

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not-a-real-mp4")

    result = analyze_clip(clip, settings, with_vision=True, keyframes_dir=tmp_path)

    assert len(result.scenes) == 2
    for scene in result.scenes:
        assert scene.description.startswith("description for ")
        assert scene.tags == ["tagA", "tagB"]
        assert scene.keyframe_path is not None
        assert scene.keyframe_path.exists()
    assert len(captured_keyframes) == 2


def test_analyze_clip_no_vision_skips_vision_calls(settings, stub_metadata_and_transcribe, tmp_path, monkeypatch):
    """When with_vision=False, scenes still detect but vision is never called."""
    fake_scenes = [SceneSegment(start=0.0, end=5.0)]
    monkeypatch.setattr("vlogkit.analyze.pipeline.detect_scenes", lambda p: fake_scenes)

    describe_calls = 0
    extract_calls = 0

    def fake_describe(*a, **k):
        nonlocal describe_calls
        describe_calls += 1
        return ("should not appear", [])

    def fake_extract_keyframe(*a, **k):
        nonlocal extract_calls
        extract_calls += 1
        return Path("nowhere.jpg")

    monkeypatch.setattr("vlogkit.analyze.pipeline.describe_keyframe", fake_describe)
    monkeypatch.setattr("vlogkit.analyze.pipeline.extract_keyframe", fake_extract_keyframe)

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not-a-real-mp4")

    result = analyze_clip(clip, settings, with_vision=False, keyframes_dir=tmp_path)

    assert len(result.scenes) == 1
    assert result.scenes[0].description == ""
    assert result.scenes[0].tags == []
    assert describe_calls == 0
    assert extract_calls == 0


def test_analyze_clip_no_api_key_skips_vision_even_when_requested(stub_metadata_and_transcribe, tmp_path, monkeypatch):
    """With no API key, vision is skipped even if with_vision=True (graceful degradation)."""
    fake_scenes = [SceneSegment(start=0.0, end=5.0)]
    monkeypatch.setattr("vlogkit.analyze.pipeline.detect_scenes", lambda p: fake_scenes)

    describe_calls = 0

    def fake_describe(*a, **k):
        nonlocal describe_calls
        describe_calls += 1
        return ("should not appear", [])

    monkeypatch.setattr("vlogkit.analyze.pipeline.describe_keyframe", fake_describe)

    settings_no_key = Settings(anthropic_api_key="")
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not-a-real-mp4")

    result = analyze_clip(clip, settings_no_key, with_vision=True, keyframes_dir=tmp_path)

    assert len(result.scenes) == 1
    assert describe_calls == 0
