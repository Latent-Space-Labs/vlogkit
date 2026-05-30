"""Tests for audio cleanup + text overlay features in vlogkit.captions.render."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from vlogkit.captions.render import (
    build_ffmpeg_command,
    render,
    _escape_drawtext,
)
from vlogkit.models import Storyboard, StoryboardSection, StoryboardSegment

FF_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"


def _seg(path: str, in_p: float = 0.0, out_p: float = 1.0, label: str = "") -> StoryboardSegment:
    return StoryboardSegment(
        clip_path=Path(path), in_point=in_p, out_point=out_p, label=label, include=True
    )


def _filtergraph(cmd: list[str]) -> str:
    return cmd[cmd.index("-filter_complex") + 1]


def _maps(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-map"]


# ---------------------------------------------------------------------------
# Regression: all new params default-off => byte-identical legacy output
# ---------------------------------------------------------------------------


def test_all_new_params_default_is_byte_identical():
    segs = [_seg("a.mp4", 0.0, 1.0, label="One"), _seg("b.mp4", 2.0, 4.5, label="Two")]
    baseline = build_ffmpeg_command(segs, None, Path("out.mp4"))
    with_defaults = build_ffmpeg_command(
        segs,
        None,
        Path("out.mp4"),
        audio_cleanup=False,
        denoise=False,
        title_card=None,
        lower_thirds=False,
    )
    assert with_defaults == baseline
    fg = _filtergraph(with_defaults)
    assert "loudnorm" not in fg
    assert "afftdn" not in fg
    assert "drawtext" not in fg
    assert _maps(with_defaults) == ["[vc]", "[ac]"]


# ---------------------------------------------------------------------------
# Audio cleanup / denoise
# ---------------------------------------------------------------------------


def test_audio_cleanup_adds_loudnorm_and_remaps():
    segs = [_seg("a.mp4")]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"), audio_cleanup=True)
    fg = _filtergraph(cmd)
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in fg
    assert "afftdn" not in fg
    maps = _maps(cmd)
    # audio map points at the post-audio output, not raw [ac]
    assert "[ac]" not in maps
    assert "[aout]" in maps


def test_denoise_adds_afftdn_before_loudnorm():
    segs = [_seg("a.mp4")]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"), audio_cleanup=True, denoise=True)
    fg = _filtergraph(cmd)
    assert "afftdn=nf=-25" in fg
    assert "loudnorm=I=-14:TP=-1.5:LRA=11" in fg
    assert fg.index("afftdn") < fg.index("loudnorm")
    assert "[aout]" in _maps(cmd)


def test_denoise_alone_builds_post_audio_stage():
    segs = [_seg("a.mp4")]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"), denoise=True)
    fg = _filtergraph(cmd)
    assert "afftdn=nf=-25" in fg
    assert "loudnorm" not in fg
    assert "[aout]" in _maps(cmd)


def test_no_audio_cleanup_keeps_raw_ac_map():
    segs = [_seg("a.mp4")]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"))
    fg = _filtergraph(cmd)
    assert "loudnorm" not in fg
    assert "afftdn" not in fg
    assert _maps(cmd) == ["[vc]", "[ac]"]


# ---------------------------------------------------------------------------
# Title card
# ---------------------------------------------------------------------------


def test_title_card_adds_drawtext_on_video():
    segs = [_seg("a.mp4")]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"), title_card="Hello")
    fg = _filtergraph(cmd)
    assert "drawtext" in fg
    assert "text='Hello'" in fg
    assert "enable='lt(t,3)'" in fg
    # centered
    assert "x=(w-text_w)/2" in fg
    assert "y=(h-text_h)/2" in fg


def test_title_card_applies_after_subtitles():
    segs = [_seg("a.mp4")]
    cmd = build_ffmpeg_command(
        segs, Path("/tmp/s.srt"), Path("out.mp4"), title_card="Hi"
    )
    fg = _filtergraph(cmd)
    assert "subtitles=" in fg
    assert "drawtext" in fg
    # drawtext title runs on the subtitled video, after the subtitles filter
    assert fg.index("subtitles=") < fg.index("drawtext")
    # final video map is the title output, not [vc]/[vout]
    maps = _maps(cmd)
    assert maps[0] not in ("[vc]", "[vout]")


def test_title_card_escapes_special_chars():
    segs = [_seg("a.mp4")]
    cmd = build_ffmpeg_command(
        segs, None, Path("out.mp4"), title_card="Day: it's 50%"
    )
    fg = _filtergraph(cmd)
    # colon escaped, apostrophe escaped, percent escaped
    assert "Day\\:" in fg
    assert "it\\'s" in fg
    assert "50\\%" in fg


# ---------------------------------------------------------------------------
# Lower thirds
# ---------------------------------------------------------------------------


def test_lower_thirds_adds_drawtext_to_labeled_segment():
    segs = [_seg("a.mp4", label="Intro"), _seg("b.mp4", label="")]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"), lower_thirds=True)
    fg = _filtergraph(cmd)
    # the labeled segment gets a drawtext
    assert "drawtext" in fg
    assert "text='Intro'" in fg
    # exactly one drawtext (only the labeled segment), no title card here
    assert fg.count("drawtext") == 1


def test_lower_thirds_skips_unlabeled_segments():
    segs = [_seg("a.mp4", label=""), _seg("b.mp4", label="")]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"), lower_thirds=True)
    fg = _filtergraph(cmd)
    assert "drawtext" not in fg


def test_lower_thirds_off_adds_no_drawtext():
    segs = [_seg("a.mp4", label="Intro")]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"), lower_thirds=False)
    fg = _filtergraph(cmd)
    assert "drawtext" not in fg


# ---------------------------------------------------------------------------
# _escape_drawtext
# ---------------------------------------------------------------------------


def test_escape_drawtext_handles_all_special_chars():
    out = _escape_drawtext("a\\b:c'd%e")
    assert "\\\\" in out  # backslash doubled
    assert "\\:" in out
    assert "\\'" in out
    assert "\\%" in out


# ---------------------------------------------------------------------------
# Guarded real E2E
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not Path(FF_FULL).exists(), reason="ffmpeg-full not installed")
def test_render_e2e_audio_cleanup_and_title(tmp_path):
    import subprocess

    clip = tmp_path / "a.mp4"
    subprocess.run(
        [FF_FULL, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "testsrc=size=320x240:rate=30:d=1", "-f", "lavfi",
         "-i", "sine=frequency=440:d=1", "-shortest", "-pix_fmt", "yuv420p",
         str(clip), "-y"],
        check=True,
    )
    sb = Storyboard(sections=[StoryboardSection(title="s", segments=[
        StoryboardSegment(clip_path=clip, in_point=0.0, out_point=1.0)])])
    out = render(
        sb, tmp_path / "out.mp4", fps=30.0, ffmpeg_bin=FF_FULL,
        audio_cleanup=True, title_card="Hi",
    )
    assert out.exists() and out.stat().st_size > 0
