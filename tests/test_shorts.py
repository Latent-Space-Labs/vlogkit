"""Tests for the vertical Shorts extraction module (TDD)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from vlogkit.models import (
    ClipAnalysis,
    ClipMetadata,
    MurchScore,
    SceneSegment,
)
from vlogkit.repurpose import shorts

FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _murch(impact: float = 0.0, composite: float = 0.0) -> MurchScore:
    return MurchScore(
        scene_type="hook",
        aesthetic=0.0,
        credibility=0.0,
        impact=impact,
        memorability=0.0,
        fun=0.0,
        composite=composite,
    )


def _scene(start: float, end: float, *, impact=None, composite=None, murch=True) -> SceneSegment:
    m = None
    if murch:
        m = _murch(impact=impact or 0.0, composite=composite or 0.0)
    return SceneSegment(start=start, end=end, murch=m)


def _analysis(path: str, scenes: list[SceneSegment], duration: float = 120.0) -> ClipAnalysis:
    meta = ClipMetadata(
        filename=Path(path).name,
        path=Path(path),
        duration=duration,
        resolution=(1920, 1080),
        fps=30.0,
        file_size=1000,
    )
    return ClipAnalysis(metadata=meta, scenes=scenes)


# --------------------------------------------------------------------------- #
# pick_short_window
# --------------------------------------------------------------------------- #
def test_pick_empty_returns_none():
    assert shorts.pick_short_window([]) is None


def test_pick_no_scenes_returns_none():
    a = _analysis("/clips/a.mp4", [])
    assert shorts.pick_short_window([a]) is None


def test_pick_single_window_in_range():
    # one clip, three scenes spanning 30s total -> whole run qualifies
    scenes = [
        _scene(0, 10, impact=50),
        _scene(10, 20, impact=60),
        _scene(20, 30, impact=70),
    ]
    a = _analysis("/clips/a.mp4", scenes)
    result = shorts.pick_short_window([a], min_dur=15, max_dur=60)
    assert result is not None
    path, start, end = result
    assert path == Path("/clips/a.mp4")
    assert start == 0
    assert end == 30


def test_pick_selects_highest_impact_run():
    # Many short scenes; window must be a contiguous run within [min,max].
    # Scenes 0-2 are low impact, scenes 3-5 high impact. Each scene 8s.
    scenes = [
        _scene(0, 8, impact=1),
        _scene(8, 16, impact=1),
        _scene(16, 24, impact=1),
        _scene(24, 32, impact=90),
        _scene(32, 40, impact=90),
        _scene(40, 48, impact=90),
    ]
    a = _analysis("/clips/a.mp4", scenes)
    result = shorts.pick_short_window([a], min_dur=15, max_dur=24)
    assert result is not None
    _, start, end = result
    # best 3-scene (24s) run is scenes 3..5 -> [24, 48]
    assert start == 24
    assert end == 48


def test_pick_uses_composite_when_impact_zero():
    scenes = [
        _scene(0, 10, composite=10),
        _scene(10, 20, composite=99),
    ]
    a = _analysis("/clips/a.mp4", scenes)
    result = shorts.pick_short_window([a], min_dur=10, max_dur=10)
    assert result is not None
    _, start, end = result
    # single-scene windows of len 10; second scene scores higher via composite
    assert start == 10
    assert end == 20


def test_pick_treats_none_murch_as_zero():
    scenes = [
        _scene(0, 20, murch=False),  # None murch -> 0
        _scene(20, 40, impact=5),
    ]
    a = _analysis("/clips/a.mp4", scenes)
    result = shorts.pick_short_window([a], min_dur=20, max_dur=20)
    assert result is not None
    _, start, end = result
    assert start == 20
    assert end == 40


def test_pick_clamps_single_scene_over_max():
    # A single scene is 90s long, exceeding max_dur=60 -> clamp from its start.
    scenes = [_scene(5, 95, impact=50)]
    a = _analysis("/clips/a.mp4", scenes)
    result = shorts.pick_short_window([a], min_dur=15, max_dur=60)
    assert result is not None
    _, start, end = result
    assert start == 5
    assert end == 65  # start + max_dur


def test_pick_fallback_full_span_below_min():
    # Total footage (8s) is below min_dur=15 -> still return full span.
    scenes = [_scene(0, 4, impact=10), _scene(4, 8, impact=10)]
    a = _analysis("/clips/a.mp4", scenes)
    result = shorts.pick_short_window([a], min_dur=15, max_dur=60)
    assert result is not None
    path, start, end = result
    assert path == Path("/clips/a.mp4")
    assert start == 0
    assert end == 8


def test_pick_does_not_cross_clips():
    # Two clips each with 10s footage; min_dur=15 cannot be met by either,
    # so we fall back to the best single clip's full span (not a cross-clip run).
    a = _analysis("/clips/a.mp4", [_scene(0, 10, impact=5)])
    b = _analysis("/clips/b.mp4", [_scene(0, 10, impact=80)])
    result = shorts.pick_short_window([a, b], min_dur=15, max_dur=60)
    assert result is not None
    path, start, end = result
    assert path == Path("/clips/b.mp4")
    assert start == 0
    assert end == 10


def test_pick_best_clip_across_clips_in_range():
    a = _analysis("/clips/a.mp4", [_scene(0, 20, impact=10), _scene(20, 40, impact=10)])
    b = _analysis("/clips/b.mp4", [_scene(0, 20, impact=90), _scene(20, 40, impact=90)])
    result = shorts.pick_short_window([a, b], min_dur=15, max_dur=60)
    assert result is not None
    path, _, _ = result
    assert path == Path("/clips/b.mp4")


# --------------------------------------------------------------------------- #
# build_vertical_command
# --------------------------------------------------------------------------- #
def test_build_command_single_input_and_output():
    cmd = shorts.build_vertical_command(
        Path("/clips/a.mp4"), 5.0, 20.0, Path("/out/short.mp4"), None
    )
    # exactly one -i input
    assert cmd.count("-i") == 1
    i = cmd.index("-i")
    assert cmd[i + 1] == "/clips/a.mp4"
    # output last, preceded by -y
    assert cmd[-1] == "/out/short.mp4"
    assert "-y" in cmd
    assert cmd[cmd.index("-y") + 1] == "/out/short.mp4"


def test_build_command_crop_fill_filter():
    cmd = shorts.build_vertical_command(
        Path("/clips/a.mp4"), 0.0, 10.0, Path("/out/s.mp4"), None,
        resolution=(1080, 1920), fps=30.0,
    )
    fc = _filtergraph(cmd)
    # trim with setpts reset
    assert "trim=start=0.0:end=10.0" in fc
    assert "setpts=PTS-STARTPTS" in fc
    # center-crop fill (no bars): scale increase then crop to target
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in fc
    assert "crop=1080:1920" in fc
    assert "setsar=1" in fc
    assert "fps=30.0" in fc
    # no letterbox pad
    assert "pad=" not in fc


def test_build_command_codecs_and_fps():
    cmd = shorts.build_vertical_command(
        Path("/clips/a.mp4"), 0.0, 10.0, Path("/out/s.mp4"), None, fps=24.0
    )
    assert "libx264" in cmd
    assert "yuv420p" in cmd
    assert "aac" in cmd
    assert "-r" in cmd
    assert cmd[cmd.index("-r") + 1] == "24.0"


def test_build_command_no_subtitles():
    cmd = shorts.build_vertical_command(
        Path("/clips/a.mp4"), 0.0, 10.0, Path("/out/s.mp4"), None
    )
    fc = _filtergraph(cmd)
    assert "subtitles=" not in fc


def test_build_command_with_subtitles():
    cmd = shorts.build_vertical_command(
        Path("/clips/a.mp4"), 0.0, 10.0, Path("/out/s.mp4"),
        Path("/out/caps.ass"),
    )
    fc = _filtergraph(cmd)
    assert "subtitles=" in fc
    assert "caps.ass" in fc


def test_build_command_escapes_subtitle_path():
    cmd = shorts.build_vertical_command(
        Path("/clips/a.mp4"), 0.0, 10.0, Path("/out/s.mp4"),
        Path("/weird/C:colon/caps.ass"),
    )
    fc = _filtergraph(cmd)
    # colon must be escaped inside the subtitles filter
    assert "\\:" in fc


def test_build_command_custom_ffmpeg_bin():
    cmd = shorts.build_vertical_command(
        Path("/clips/a.mp4"), 0.0, 10.0, Path("/out/s.mp4"), None,
        ffmpeg_bin="/opt/ff/ffmpeg",
    )
    assert cmd[0] == "/opt/ff/ffmpeg"


def _filtergraph(cmd: list[str]) -> str:
    """Return the -filter_complex / -vf argument from an ffmpeg argv."""
    for flag in ("-filter_complex", "-vf"):
        if flag in cmd:
            return cmd[cmd.index(flag) + 1]
    raise AssertionError(f"no filter graph flag in command: {cmd}")


# --------------------------------------------------------------------------- #
# make_short end-to-end (real ffmpeg)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    not FFMPEG_FULL.exists() and shutil.which("ffmpeg") is None,
    reason="ffmpeg not available",
)
def test_make_short_end_to_end(tmp_path):
    from vlogkit.config import Settings
    from vlogkit.project import Project, file_hash

    ffmpeg = str(FFMPEG_FULL) if FFMPEG_FULL.exists() else shutil.which("ffmpeg")
    ffprobe = (
        str(FFMPEG_FULL.parent / "ffprobe")
        if (FFMPEG_FULL.parent / "ffprobe").exists()
        else shutil.which("ffprobe")
    )

    # Generate a ~7s horizontal test clip.
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        [
            ffmpeg, "-f", "lavfi", "-i", "testsrc=duration=7:size=1280x720:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=7",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", "-y", str(clip),
        ],
        check=True, capture_output=True,
    )

    settings = Settings()
    project = Project(tmp_path, settings=settings)
    project.init()

    meta = ClipMetadata(
        filename=clip.name,
        path=clip,
        duration=7.0,
        resolution=(1280, 720),
        fps=30.0,
        file_size=clip.stat().st_size,
        codec="h264",
    )
    analysis = ClipAnalysis(
        metadata=meta,
        scenes=[
            _scene(0, 3.5, impact=80),
            _scene(3.5, 7.0, impact=85),
        ],
        file_hash=file_hash(clip),
    )
    project.save_analysis(analysis)

    out = shorts.make_short(
        project, min_dur=3, max_dur=6, captions=False, ffmpeg_bin=ffmpeg
    )
    assert out.exists()
    assert out.stat().st_size > 0

    # Probe dimensions: must be vertical (height > width).
    probe = subprocess.run(
        [
            ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=p=0:s=x", str(out),
        ],
        check=True, capture_output=True, text=True,
    )
    w, h = (int(x) for x in probe.stdout.strip().split("x"))
    assert h > w
