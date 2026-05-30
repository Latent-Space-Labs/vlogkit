"""Tests for the captions pipeline: style loading + end-to-end file generation."""

import json
from pathlib import Path

import pytest

from vlogkit.captions.pipeline import (
    EXTENSIONS,
    ffmpeg_has_libass,
    generate_caption_file,
    load_caption_style,
)
from vlogkit.models import (
    CaptionStyle,
    ClipAnalysis,
    ClipMetadata,
    Storyboard,
    StoryboardSection,
    StoryboardSegment,
    TranscriptSegment,
    WordTimestamp,
)


def _clip(path: Path, words: list[tuple[float, float, str]]) -> ClipAnalysis:
    return ClipAnalysis(
        metadata=ClipMetadata(
            filename=path.name, path=path, duration=30.0,
            resolution=(1920, 1080), fps=30.0, file_size=1,
        ),
        transcript=[
            TranscriptSegment(
                start=words[0][0], end=words[-1][1], text=" ".join(w[2] for w in words),
                words=[WordTimestamp(start=s, end=e, word=w) for s, e, w in words],
            )
        ] if words else [],
    )


def _storyboard(clip_path: Path) -> Storyboard:
    return Storyboard(
        title="T",
        sections=[StoryboardSection(title="S", segments=[
            StoryboardSegment(clip_path=clip_path, in_point=0.0, out_point=5.0, include=True),
        ])],
    )


# --- style loading ---

def test_load_style_defaults_when_no_override(tmp_path):
    style = load_caption_style(tmp_path)
    assert isinstance(style, CaptionStyle)
    assert style.max_chars_per_line == 42


def test_load_style_merges_partial_override(tmp_path):
    cfg = tmp_path / ".vlogkit"
    cfg.mkdir()
    (cfg / "caption_style.json").write_text(json.dumps({"font_size": 72, "karaoke": True}))
    style = load_caption_style(tmp_path)
    assert style.font_size == 72
    assert style.karaoke is True
    # untouched fields keep defaults
    assert style.max_chars_per_line == 42


def test_load_style_malformed_json_falls_back(tmp_path):
    cfg = tmp_path / ".vlogkit"
    cfg.mkdir()
    (cfg / "caption_style.json").write_text("{not valid json")
    style = load_caption_style(tmp_path)
    assert style.font_size == CaptionStyle().font_size


# --- file generation ---

def test_generate_srt_file(tmp_path):
    clip = tmp_path / "a.mp4"
    clip.touch()
    analysis = _clip(clip, [(0.0, 0.5, "Hello"), (0.6, 1.0, "world")])
    out = tmp_path / "out.srt"
    result = generate_caption_file(
        _storyboard(clip), [analysis], fmt="srt", output_path=out, style=CaptionStyle()
    )
    assert result == out
    text = out.read_text()
    assert "Hello world" in text
    assert "-->" in text
    assert text.strip().startswith("1")


def test_generate_vtt_file(tmp_path):
    clip = tmp_path / "a.mp4"
    clip.touch()
    analysis = _clip(clip, [(0.0, 0.5, "Hi"), (0.6, 1.0, "there")])
    out = tmp_path / "out.vtt"
    generate_caption_file(_storyboard(clip), [analysis], fmt="vtt", output_path=out)
    assert out.read_text().startswith("WEBVTT")


def test_generate_ass_file(tmp_path):
    clip = tmp_path / "a.mp4"
    clip.touch()
    analysis = _clip(clip, [(0.0, 0.5, "Hi")])
    out = tmp_path / "out.ass"
    generate_caption_file(_storyboard(clip), [analysis], fmt="ass", output_path=out)
    assert "[Script Info]" in out.read_text()


def test_generate_unknown_format_raises(tmp_path):
    clip = tmp_path / "a.mp4"
    clip.touch()
    with pytest.raises(ValueError):
        generate_caption_file(_storyboard(clip), [_clip(clip, [(0.0, 0.5, "x")])],
                              fmt="bogus", output_path=tmp_path / "x.bogus")


def test_extensions_map_has_all_formats():
    assert set(EXTENSIONS) == {"srt", "vtt", "ass"}


def test_ffmpeg_has_libass_returns_bool():
    # Just exercises the detector; result depends on the host ffmpeg.
    assert isinstance(ffmpeg_has_libass(), bool)
