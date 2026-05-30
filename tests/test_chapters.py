"""Tests for YouTube chapters + description generation."""

from pathlib import Path

from vlogkit.publish.chapters import (
    build_chapters,
    build_description,
    chapters_to_text,
    format_timestamp,
)
from vlogkit.models import Storyboard, StoryboardSection, StoryboardSegment


def _seg(dur: float, include=True):
    return StoryboardSegment(clip_path=Path("c.mp4"), in_point=0.0, out_point=dur, include=include)


def _sb(sections):
    return Storyboard(title="My Vlog", sections=[
        StoryboardSection(title=t, segments=segs) for t, segs in sections
    ])


# --- format_timestamp ---

def test_format_timestamp_minutes():
    assert format_timestamp(0) == "0:00"
    assert format_timestamp(83) == "1:23"
    assert format_timestamp(605) == "10:05"


def test_format_timestamp_hours():
    assert format_timestamp(3661) == "1:01:01"


# --- build_chapters ---

def test_chapters_cumulative_starts_on_final_timeline():
    sb = _sb([
        ("Intro", [_seg(30)]),
        ("Main", [_seg(120)]),
        ("Outro", [_seg(20)]),
    ])
    chapters = build_chapters(sb)
    assert chapters[0] == (0.0, "Intro")
    assert chapters[1] == (30.0, "Main")
    assert chapters[2] == (150.0, "Outro")


def test_chapters_first_is_always_zero():
    # Even if the first section somehow had offset, first chapter is 0:00.
    sb = _sb([("Intro", [_seg(15)]), ("Body", [_seg(60)])])
    chapters = build_chapters(sb)
    assert chapters[0][0] == 0.0


def test_chapters_excluded_segments_dont_count():
    sb = _sb([
        ("Intro", [_seg(30), _seg(10, include=False)]),
        ("Main", [_seg(60)]),
    ])
    chapters = build_chapters(sb)
    assert chapters[1] == (30.0, "Main")  # excluded 10s not added


def test_chapters_drops_too_close_under_min_gap():
    # YouTube requires >=10s between chapters; a 5s section is folded away.
    sb = _sb([
        ("Intro", [_seg(30)]),
        ("Blip", [_seg(5)]),     # starts at 30, next starts at 35 (<10s gap) -> dropped
        ("Main", [_seg(60)]),
    ])
    chapters = build_chapters(sb, min_gap=10.0)
    starts = [s for s, _ in chapters]
    assert 35.0 not in starts
    assert (0.0, "Intro") in chapters
    assert (30.0, "Blip") in chapters  # Blip kept; Main dropped for being <10s after
    assert (35.0, "Main") not in chapters


def test_chapters_skips_empty_sections():
    sb = _sb([
        ("Intro", [_seg(30)]),
        ("Empty", []),
        ("Main", [_seg(60)]),
    ])
    chapters = build_chapters(sb)
    titles = [t for _, t in chapters]
    assert "Empty" not in titles


# --- serialization ---

def test_chapters_to_text():
    text = chapters_to_text([(0.0, "Intro"), (30.0, "Main"), (150.0, "Outro")])
    assert text == "0:00 Intro\n0:30 Main\n2:30 Outro"


def test_build_description_includes_title_and_chapters():
    sb = _sb([("Intro", [_seg(30)]), ("Main", [_seg(60)])])
    chapters = build_chapters(sb)
    desc = build_description(sb, chapters)
    assert "My Vlog" in desc
    assert "0:00 Intro" in desc
    assert "Chapters:" in desc


def test_build_description_with_intro_blurb():
    sb = _sb([("Intro", [_seg(30)]), ("Main", [_seg(60)])])
    desc = build_description(sb, build_chapters(sb), intro="A trip to the coast.")
    assert "A trip to the coast." in desc
