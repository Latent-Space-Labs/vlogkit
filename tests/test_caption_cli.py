"""Integration test for the `vlogkit captions` CLI command."""

from pathlib import Path

from typer.testing import CliRunner

from vlogkit.cli import app
from vlogkit.models import (
    ClipAnalysis,
    ClipMetadata,
    Storyboard,
    StoryboardSection,
    StoryboardSegment,
    TranscriptSegment,
    WordTimestamp,
)
from vlogkit.project import Project

runner = CliRunner()


def _setup_project(tmp_path: Path) -> Path:
    """Create an initialized project with one analyzed clip and a storyboard."""
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake-video-bytes")  # real bytes so file_hash is stable

    project = Project(tmp_path)
    project.init()

    from vlogkit.project import file_hash

    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path=clip.resolve(), duration=10.0,
            resolution=(1920, 1080), fps=30.0, file_size=clip.stat().st_size,
        ),
        transcript=[
            TranscriptSegment(
                start=0.0, end=2.0, text="Hello everyone welcome back",
                words=[
                    WordTimestamp(start=0.0, end=0.4, word="Hello"),
                    WordTimestamp(start=0.5, end=0.9, word="everyone"),
                    WordTimestamp(start=1.0, end=1.4, word="welcome"),
                    WordTimestamp(start=1.5, end=2.0, word="back"),
                ],
            )
        ],
        file_hash=file_hash(clip),
    )
    project.save_analysis(analysis)

    sb = Storyboard(
        title="Test Vlog",
        sections=[StoryboardSection(title="Intro", segments=[
            StoryboardSegment(clip_path=clip.resolve(), in_point=0.0, out_point=3.0, include=True),
        ])],
    )
    project.save_storyboard(sb)
    return tmp_path


def test_captions_srt_command(tmp_path):
    root = _setup_project(tmp_path)
    result = runner.invoke(app, ["captions", "--path", str(root), "--format", "srt"])
    assert result.exit_code == 0, result.output
    srt = root / ".vlogkit" / "captions.srt"
    assert srt.exists()
    body = srt.read_text()
    assert "Hello" in body
    assert "-->" in body


def test_captions_custom_output(tmp_path):
    root = _setup_project(tmp_path)
    out = tmp_path / "subs.vtt"
    result = runner.invoke(app, ["captions", "--path", str(root), "-f", "vtt", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_text().startswith("WEBVTT")


def test_captions_requires_storyboard(tmp_path):
    project = Project(tmp_path)
    project.init()
    result = runner.invoke(app, ["captions", "--path", str(tmp_path)])
    assert result.exit_code == 1
    assert "storyboard" in result.output.lower()


def test_captions_unknown_format(tmp_path):
    root = _setup_project(tmp_path)
    result = runner.invoke(app, ["captions", "--path", str(root), "-f", "xyz"])
    assert result.exit_code == 1
    assert "format" in result.output.lower()
