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
