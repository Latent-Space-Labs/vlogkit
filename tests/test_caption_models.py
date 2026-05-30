"""Tests for caption data models — the shared contract for the captions package."""

from vlogkit.models import CaptionCue, CaptionStyle, WordTimestamp


def test_caption_cue_minimal():
    cue = CaptionCue(start=1.0, end=3.5, text="Hello world")
    assert cue.start == 1.0
    assert cue.end == 3.5
    assert cue.text == "Hello world"
    assert cue.words == []


def test_caption_cue_with_words():
    cue = CaptionCue(
        start=1.0,
        end=2.0,
        text="hi there",
        words=[
            WordTimestamp(start=1.0, end=1.4, word="hi"),
            WordTimestamp(start=1.4, end=2.0, word="there"),
        ],
    )
    assert len(cue.words) == 2
    assert cue.words[0].word == "hi"


def test_caption_cue_roundtrip():
    cue = CaptionCue(start=0.0, end=1.0, text="a")
    assert CaptionCue.model_validate_json(cue.model_dump_json()) == cue


def test_caption_style_defaults():
    style = CaptionStyle()
    # Industry-standard readability defaults (BBC/Netflix): <=42 CPL, <=2 lines.
    assert style.max_chars_per_line == 42
    assert style.max_lines == 2
    assert style.position == "bottom"
    assert style.karaoke is False
    assert style.font_size > 0


def test_caption_style_position_constrained():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CaptionStyle(position="diagonal")  # type: ignore[arg-type]
