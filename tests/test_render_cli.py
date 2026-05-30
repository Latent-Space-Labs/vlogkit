"""Integration tests for the `vlogkit render` CLI command."""

import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vlogkit.cli import _parse_resolution, app
from vlogkit.models import (
    ClipAnalysis,
    ClipMetadata,
    Storyboard,
    StoryboardSection,
    StoryboardSegment,
)
from vlogkit.project import Project, file_hash

runner = CliRunner()
FF_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"


def test_parse_resolution_presets_and_custom():
    assert _parse_resolution(None) is None
    assert _parse_resolution("1080p") == (1920, 1080)
    assert _parse_resolution("720p") == (1280, 720)
    assert _parse_resolution("640x360") == (640, 360)


def test_parse_resolution_invalid():
    import typer

    with pytest.raises(typer.BadParameter):
        _parse_resolution("huge")


def test_render_requires_storyboard(tmp_path):
    project = Project(tmp_path)
    project.init()
    result = runner.invoke(app, ["render", "--path", str(tmp_path)])
    assert result.exit_code == 1
    assert "storyboard" in result.output.lower()


def _ff():
    if Path(FF_FULL).exists():
        return FF_FULL
    return shutil.which("ffmpeg")


@pytest.mark.skipif(_ff() is None, reason="no ffmpeg available")
def test_render_produces_mp4(tmp_path, monkeypatch):
    ff = _ff()
    # real clip
    clip = tmp_path / "clip.mp4"
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=640x360:rate=30:d=2", "-f", "lavfi",
                    "-i", "sine=frequency=440:d=2", "-shortest", "-pix_fmt", "yuv420p",
                    str(clip), "-y"], check=True)

    # Force the resolver to use the available ffmpeg.
    monkeypatch.setenv("VLOGKIT_FFMPEG", ff)

    project = Project(tmp_path)
    project.init()
    project.save_analysis(ClipAnalysis(
        metadata=ClipMetadata(filename="clip.mp4", path=clip.resolve(), duration=2.0,
                              resolution=(640, 360), fps=30.0, file_size=clip.stat().st_size),
        file_hash=file_hash(clip)))
    project.save_storyboard(Storyboard(title="R", sections=[StoryboardSection(
        title="s", segments=[StoryboardSegment(clip_path=clip.resolve(), in_point=0.0,
                                               out_point=1.5, include=True)])]))

    out = tmp_path / "final.mp4"
    result = runner.invoke(app, ["render", "--path", str(tmp_path), "-o", str(out), "-r", "720p"])
    assert result.exit_code == 0, result.output
    assert out.exists() and out.stat().st_size > 0
