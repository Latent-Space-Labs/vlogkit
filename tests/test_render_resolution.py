"""Tests for resolution-normalized rendering (mixed-size clip concat)."""

import shutil
from pathlib import Path

import pytest

from vlogkit.captions.render import build_ffmpeg_command, pick_render_target, render
from vlogkit.models import (
    ClipAnalysis,
    ClipMetadata,
    Storyboard,
    StoryboardSection,
    StoryboardSegment,
)


def _analysis(path: Path, res, fps):
    return ClipAnalysis(metadata=ClipMetadata(
        filename=path.name, path=path, duration=10.0, resolution=res, fps=fps, file_size=1))

FF_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"


def _seg(path: Path, in_p=0.0, out_p=1.0):
    return StoryboardSegment(clip_path=path, in_point=in_p, out_point=out_p, include=True)


def test_no_resolution_keeps_legacy_command():
    cmd = build_ffmpeg_command([_seg(Path("a.mp4"))], None, Path("o.mp4"))
    fg = cmd[cmd.index("-filter_complex") + 1]
    assert "scale=" not in fg
    assert "pad=" not in fg


def test_resolution_inserts_scale_and_pad():
    cmd = build_ffmpeg_command(
        [_seg(Path("a.mp4")), _seg(Path("b.mp4"))], None, Path("o.mp4"),
        resolution=(1280, 720),
    )
    fg = cmd[cmd.index("-filter_complex") + 1]
    assert fg.count("scale=1280:720") == 2
    assert "pad=1280:720" in fg
    assert "setsar=1" in fg
    # concat still present
    assert "concat=n=2:v=1:a=1" in fg


def test_resolution_normalizes_audio_for_concat():
    cmd = build_ffmpeg_command(
        [_seg(Path("a.mp4"))], None, Path("o.mp4"), resolution=(640, 360),
    )
    fg = cmd[cmd.index("-filter_complex") + 1]
    assert "aformat=" in fg


def test_pick_render_target_uses_largest_clip(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    sb = Storyboard(sections=[StoryboardSection(title="s", segments=[
        _seg(a), _seg(b)])])
    analyses = [
        _analysis(a.resolve(), (1280, 720), 30.0),
        _analysis(b.resolve(), (1920, 1080), 24.0),
    ]
    res, fps = pick_render_target(sb, analyses)
    # picks the largest frame area among included clips
    assert res == (1920, 1080)
    assert fps == 24.0  # fps of the chosen (largest) clip


def test_pick_render_target_defaults_when_no_analysis(tmp_path):
    a = tmp_path / "a.mp4"
    sb = Storyboard(sections=[StoryboardSection(title="s", segments=[_seg(a)])])
    res, fps = pick_render_target(sb, [], default_res=(1920, 1080), default_fps=30.0)
    assert res == (1920, 1080)
    assert fps == 30.0


@pytest.mark.skipif(not Path(FF_FULL).exists() and shutil.which("ffmpeg") is None,
                    reason="no ffmpeg available")
def test_render_mixed_resolution_clips(tmp_path):
    """Two clips of DIFFERENT sizes must concat cleanly when a resolution is set."""
    ff = FF_FULL if Path(FF_FULL).exists() else "ffmpeg"
    import subprocess

    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=640x480:rate=30:d=1", "-f", "lavfi",
                    "-i", "sine=frequency=440:d=1", "-shortest", "-pix_fmt", "yuv420p",
                    str(a), "-y"], check=True)
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=1280x720:rate=30:d=1", "-f", "lavfi",
                    "-i", "sine=frequency=660:d=1", "-shortest", "-pix_fmt", "yuv420p",
                    str(b), "-y"], check=True)

    sb = Storyboard(sections=[StoryboardSection(title="s", segments=[
        _seg(a, 0.0, 1.0), _seg(b, 0.0, 1.0)])])
    out = render(sb, tmp_path / "out.mp4", resolution=(1280, 720), fps=30.0, ffmpeg_bin=ff)
    assert out.exists() and out.stat().st_size > 0
