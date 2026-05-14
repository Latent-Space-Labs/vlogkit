"""Tests for data models."""

from pathlib import Path

from vlogkit.models import (
    ClipAnalysis,
    ClipMetadata,
    Storyboard,
    StoryboardSection,
    StoryboardSegment,
    TranscriptSegment,
)


def test_clip_metadata():
    meta = ClipMetadata(
        filename="test.mp4",
        path=Path("/tmp/test.mp4"),
        duration=120.5,
        resolution=(1920, 1080),
        fps=29.97,
        file_size=1024000,
    )
    assert meta.duration == 120.5
    assert meta.resolution == (1920, 1080)


def test_storyboard_included_duration():
    sb = Storyboard(
        title="Test",
        sections=[
            StoryboardSection(
                title="Section 1",
                segments=[
                    StoryboardSegment(
                        clip_path=Path("a.mp4"),
                        in_point=0, out_point=10, include=True,
                    ),
                    StoryboardSegment(
                        clip_path=Path("b.mp4"),
                        in_point=5, out_point=15, include=False,
                    ),
                    StoryboardSegment(
                        clip_path=Path("c.mp4"),
                        in_point=0, out_point=20, include=True,
                    ),
                ],
            ),
        ],
    )
    assert sb.included_duration() == 30.0


def test_clip_analysis_roundtrip():
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="test.mp4",
            path=Path("/tmp/test.mp4"),
            duration=60.0,
            resolution=(1920, 1080),
            fps=30.0,
            file_size=500000,
        ),
        transcript=[
            TranscriptSegment(start=0.0, end=5.0, text="Hello world"),
        ],
        summary="Hello world",
        file_hash="abc123",
    )
    json_str = analysis.model_dump_json()
    restored = ClipAnalysis.model_validate_json(json_str)
    assert restored.metadata.filename == "test.mp4"
    assert len(restored.transcript) == 1
    assert restored.transcript[0].text == "Hello world"


def test_scene_segment_default_murch_is_none():
    """SceneSegment.murch defaults to None — backward compat with old cache files."""
    from vlogkit.models import SceneSegment

    scene = SceneSegment(start=0.0, end=5.0)
    assert scene.murch is None


def test_scene_segment_loads_old_cache_without_murch_key():
    """Old cached JSON (pre-Plan-2) lacking 'murch' key still loads cleanly."""
    from vlogkit.models import SceneSegment

    old_json = {"start": 0.0, "end": 5.0, "description": "old", "tags": ["a"], "energy_score": 0.5}
    scene = SceneSegment.model_validate(old_json)
    assert scene.murch is None
    assert scene.description == "old"


def test_murch_score_round_trip():
    """MurchScore serializes and deserializes cleanly with all required fields."""
    from vlogkit.models import MurchScore

    score = MurchScore(
        scene_type="hook",
        aesthetic=80.0,
        credibility=70.0,
        impact=90.0,
        memorability=85.0,
        fun=60.0,
        composite=82.5,
        rationale="strong opener",
    )
    dumped = score.model_dump()
    assert dumped["scene_type"] == "hook"
    assert dumped["composite"] == 82.5

    reloaded = MurchScore.model_validate(dumped)
    assert reloaded == score


def test_murch_score_rejects_invalid_scene_type():
    """SceneType is constrained to four literals."""
    import pytest
    from pydantic import ValidationError

    from vlogkit.models import MurchScore

    with pytest.raises(ValidationError):
        MurchScore(
            scene_type="invalid",  # type: ignore[arg-type]
            aesthetic=0, credibility=0, impact=0, memorability=0, fun=0, composite=0,
        )


def test_scene_segment_serializes_with_murch():
    """SceneSegment with a MurchScore round-trips through JSON."""
    from vlogkit.models import MurchScore, SceneSegment

    scene = SceneSegment(
        start=0.0, end=5.0,
        murch=MurchScore(
            scene_type="aesthetic", aesthetic=90, credibility=50, impact=40,
            memorability=70, fun=20, composite=68.5,
        ),
    )
    dumped_json = scene.model_dump_json()
    reloaded = SceneSegment.model_validate_json(dumped_json)
    assert reloaded.murch is not None
    assert reloaded.murch.scene_type == "aesthetic"
    assert reloaded.murch.composite == 68.5
