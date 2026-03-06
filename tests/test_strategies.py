"""Tests for fallback storyboard strategies."""

from datetime import datetime, timezone
from pathlib import Path

from vlogkit.models import ClipAnalysis, ClipMetadata
from vlogkit.storyboard.strategies import chronological_fallback


def _make_analysis(name: str, duration: float, creation_time: datetime | None = None) -> ClipAnalysis:
    return ClipAnalysis(
        metadata=ClipMetadata(
            filename=name,
            path=Path(f"/tmp/{name}"),
            duration=duration,
            resolution=(1920, 1080),
            fps=30.0,
            creation_time=creation_time,
            file_size=1000,
        ),
        file_hash="test",
    )


def test_chronological_fallback():
    analyses = [
        _make_analysis("c.mp4", 30.0, datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)),
        _make_analysis("a.mp4", 20.0, datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)),
        _make_analysis("b.mp4", 10.0, datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)),
    ]
    sb = chronological_fallback(analyses)
    assert len(sb.sections) == 1
    filenames = [s.clip_path.name for s in sb.sections[0].segments]
    assert filenames == ["a.mp4", "b.mp4", "c.mp4"]
    assert sb.total_duration == 60.0
