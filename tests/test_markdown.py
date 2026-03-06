"""Tests for Markdown storyboard round-trip."""

from pathlib import Path

from vlogkit.interactive.markdown import markdown_to_storyboard, storyboard_to_markdown
from vlogkit.models import Storyboard, StoryboardSection, StoryboardSegment


def _make_storyboard() -> Storyboard:
    return Storyboard(
        title="Weekend Trip",
        sections=[
            StoryboardSection(
                title="Morning Hike",
                notes="Opens with energy",
                segments=[
                    StoryboardSegment(
                        clip_path=Path("CLIP_012.mp4"),
                        in_point=15, out_point=102,
                        label="Trail head, group stretching",
                        include=True,
                    ),
                    StoryboardSegment(
                        clip_path=Path("CLIP_013.mp4"),
                        in_point=5, out_point=22,
                        label="Walking, not much happening",
                        include=False,
                    ),
                ],
            ),
        ],
        total_duration=104.0,
        llm_rationale="Test rationale",
    )


def test_storyboard_to_markdown():
    sb = _make_storyboard()
    md = storyboard_to_markdown(sb)
    assert "# Weekend Trip" in md
    assert "## Morning Hike" in md
    assert "[x] CLIP_012.mp4" in md
    assert "[ ] CLIP_013.mp4" in md
    assert "[0:15 - 1:42]" in md


def test_markdown_roundtrip():
    sb = _make_storyboard()
    md = storyboard_to_markdown(sb)
    restored = markdown_to_storyboard(md)
    assert restored.title == "Weekend Trip"
    assert len(restored.sections) == 1
    assert len(restored.sections[0].segments) == 2
    assert restored.sections[0].segments[0].include is True
    assert restored.sections[0].segments[1].include is False
    assert restored.sections[0].segments[0].in_point == 15
    assert restored.sections[0].segments[0].out_point == 102


def test_markdown_toggle_inclusion():
    md = """# My Vlog

## Section 1
- [x] clip1.mp4 [0:00 - 0:30] "First clip"
- [ ] clip2.mp4 [0:05 - 0:20] "Second clip"
"""
    sb = markdown_to_storyboard(md)
    # Toggle clip2 to included
    sb.sections[0].segments[1].include = True
    md2 = storyboard_to_markdown(sb)
    assert "[x] clip2.mp4" in md2
