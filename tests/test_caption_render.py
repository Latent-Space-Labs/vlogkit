"""Tests for vlogkit.captions.render — ffmpeg command building and rendering."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from vlogkit.captions import render as render_mod
from vlogkit.captions.render import (
    build_ffmpeg_command,
    included_segments,
    render,
    _escape_subtitle_path,
)
from vlogkit.models import Storyboard, StoryboardSection, StoryboardSegment


# ---------------------------------------------------------------------------
# included_segments
# ---------------------------------------------------------------------------


def _seg(path: str, in_p: float, out_p: float, include: bool = True) -> StoryboardSegment:
    return StoryboardSegment(
        clip_path=Path(path), in_point=in_p, out_point=out_p, include=include
    )


def test_included_segments_filters_and_orders():
    sb = Storyboard(
        title="T",
        sections=[
            StoryboardSection(
                title="A",
                segments=[
                    _seg("a.mp4", 0.0, 1.0, include=True),
                    _seg("b.mp4", 1.0, 2.0, include=False),
                ],
            ),
            StoryboardSection(
                title="B",
                segments=[
                    _seg("c.mp4", 2.0, 3.0, include=True),
                ],
            ),
        ],
    )
    segs = included_segments(sb)
    assert [str(s.clip_path) for s in segs] == ["a.mp4", "c.mp4"]


def test_included_segments_empty():
    sb = Storyboard(title="T", sections=[])
    assert included_segments(sb) == []


# ---------------------------------------------------------------------------
# _escape_subtitle_path
# ---------------------------------------------------------------------------


def test_escape_subtitle_path_colon_and_space():
    p = Path("/tmp/my dir/sub:file.srt")
    escaped = _escape_subtitle_path(p)
    # Returns filename='...' form
    assert escaped.startswith("filename='")
    assert escaped.endswith("'")
    # colon must be escaped for the filtergraph
    assert "\\:" in escaped
    # the space is preserved inside the quotes
    assert "my dir" in escaped


def test_escape_subtitle_path_backslash_and_quote():
    p = Path("/tmp/o'brien/a\\b.srt")
    escaped = _escape_subtitle_path(p)
    # single quote escaped
    assert "\\'" in escaped or "\\\\'" in escaped
    # backslash escaped (doubled)
    assert "\\\\" in escaped


# ---------------------------------------------------------------------------
# build_ffmpeg_command — pure
# ---------------------------------------------------------------------------


def test_build_command_input_count():
    segs = [_seg("a.mp4", 0.0, 1.0), _seg("b.mp4", 2.0, 4.5)]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"))
    assert cmd[0] == "ffmpeg"
    # two -i inputs
    i_positions = [i for i, tok in enumerate(cmd) if tok == "-i"]
    assert len(i_positions) == 2
    assert cmd[i_positions[0] + 1] == "a.mp4"
    assert cmd[i_positions[1] + 1] == "b.mp4"


def test_build_command_ffmpeg_bin_override():
    segs = [_seg("a.mp4", 0.0, 1.0)]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"), ffmpeg_bin="/usr/bin/ffmpeg")
    assert cmd[0] == "/usr/bin/ffmpeg"


def _filtergraph(cmd: list[str]) -> str:
    idx = cmd.index("-filter_complex")
    return cmd[idx + 1]


def test_build_command_trim_values_present():
    segs = [_seg("a.mp4", 0.5, 1.25), _seg("b.mp4", 2.0, 4.5)]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"))
    fg = _filtergraph(cmd)
    assert "trim=start=0.5:end=1.25" in fg
    assert "atrim=start=0.5:end=1.25" in fg
    assert "trim=start=2.0:end=4.5" in fg
    assert "atrim=start=2.0:end=4.5" in fg
    assert "setpts=PTS-STARTPTS" in fg
    assert "asetpts=PTS-STARTPTS" in fg


def test_build_command_concat_count():
    segs = [_seg("a.mp4", 0.0, 1.0), _seg("b.mp4", 0.0, 1.0), _seg("c.mp4", 0.0, 1.0)]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"))
    fg = _filtergraph(cmd)
    assert "concat=n=3:v=1:a=1" in fg
    # interleaved labels
    assert "[v0][a0][v1][a1][v2][a2]" in fg


def test_build_command_no_subtitles_maps_concat_output():
    segs = [_seg("a.mp4", 0.0, 1.0)]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"))
    fg = _filtergraph(cmd)
    assert "subtitles=" not in fg
    # maps point at concat outputs
    map_targets = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-map"]
    assert map_targets == ["[vc]", "[ac]"]


def test_build_command_with_subtitles_adds_filter_and_maps_vout():
    segs = [_seg("a.mp4", 0.0, 1.0)]
    cmd = build_ffmpeg_command(segs, Path("/tmp/s.srt"), Path("out.mp4"))
    fg = _filtergraph(cmd)
    assert "subtitles=" in fg
    assert "[vc]subtitles=" in fg
    assert "[vout]" in fg
    map_targets = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-map"]
    assert map_targets == ["[vout]", "[ac]"]


def test_build_command_output_and_flags():
    segs = [_seg("a.mp4", 0.0, 1.0)]
    cmd = build_ffmpeg_command(segs, None, Path("out.mp4"), fps=24.0)
    assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "libx264"
    assert "-pix_fmt" in cmd and cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "aac"
    assert "-r" in cmd and cmd[cmd.index("-r") + 1] == "24.0"
    # -y immediately before output path, output is last token
    assert cmd[-1] == "out.mp4"
    assert cmd[-2] == "-y"


# ---------------------------------------------------------------------------
# render — real end-to-end with ffmpeg
# ---------------------------------------------------------------------------


def _has_subtitles_filter() -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False
    out = subprocess.run(
        [ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True
    ).stdout
    return "subtitles" in out


def _make_clip(path: Path, color: str, dur: float = 1.0) -> None:
    cmd = [
        "ffmpeg",
        "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d={dur}",
        "-f", "lavfi", "-i", f"sine=frequency=440:d={dur}",
        "-shortest", "-y", str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def test_render_no_segments_raises():
    sb = Storyboard(title="empty", sections=[])
    with pytest.raises(RuntimeError):
        render(sb, Path("/tmp/should_not_exist.mp4"))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_render_end_to_end_no_subtitles(tmp_path):
    clip1 = tmp_path / "red.mp4"
    clip2 = tmp_path / "blue.mp4"
    _make_clip(clip1, "red", 1.0)
    _make_clip(clip2, "blue", 1.0)

    sb = Storyboard(
        title="E2E",
        sections=[
            StoryboardSection(
                title="S",
                segments=[
                    StoryboardSegment(clip_path=clip1, in_point=0.0, out_point=0.5),
                    StoryboardSegment(clip_path=clip2, in_point=0.0, out_point=0.5),
                ],
            )
        ],
    )
    out = tmp_path / "out.mp4"
    result = render(sb, out)
    assert result == out
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_render_end_to_end_with_subtitles(tmp_path):
    clip1 = tmp_path / "red.mp4"
    _make_clip(clip1, "red", 1.0)

    srt = tmp_path / "subs.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:00,500\nHello vlog\n\n",
        encoding="utf-8",
    )

    sb = Storyboard(
        title="E2E-subs",
        sections=[
            StoryboardSection(
                title="S",
                segments=[
                    StoryboardSegment(clip_path=clip1, in_point=0.0, out_point=0.5),
                ],
            )
        ],
    )
    out = tmp_path / "out_subs.mp4"

    if _has_subtitles_filter():
        # libass present: burn-in path should produce a real file.
        result = render(sb, out, subtitle_path=srt)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 0
    else:
        # This ffmpeg build lacks the `subtitles` filter (no libass).
        # The command is still built correctly; ffmpeg reports the missing
        # filter and render() surfaces it as a clear RuntimeError.
        with pytest.raises(RuntimeError, match="subtitles|Filter not found"):
            render(sb, out, subtitle_path=srt)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_render_missing_ffmpeg_bin_raises(tmp_path):
    clip1 = tmp_path / "red.mp4"
    _make_clip(clip1, "red", 1.0)
    sb = Storyboard(
        title="x",
        sections=[
            StoryboardSection(
                title="S",
                segments=[
                    StoryboardSegment(clip_path=clip1, in_point=0.0, out_point=0.5),
                ],
            )
        ],
    )
    with pytest.raises(RuntimeError, match="not found|ffmpeg"):
        render(sb, tmp_path / "out.mp4", ffmpeg_bin="definitely-not-ffmpeg-xyz")
