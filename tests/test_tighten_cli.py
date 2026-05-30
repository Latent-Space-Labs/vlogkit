"""Integration test for the `vlogkit tighten` CLI command."""

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
from vlogkit.project import Project, file_hash

runner = CliRunner()


def _setup(tmp_path: Path) -> Path:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake-video-bytes")
    project = Project(tmp_path)
    project.init()
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path=clip.resolve(), duration=10.0,
            resolution=(1920, 1080), fps=30.0, file_size=clip.stat().st_size,
        ),
        transcript=[TranscriptSegment(
            start=0.0, end=2.0, text="Hello um world",
            words=[
                WordTimestamp(start=0.0, end=0.5, word="Hello"),
                WordTimestamp(start=0.6, end=0.9, word="um"),
                WordTimestamp(start=1.0, end=2.0, word="world"),
            ],
        )],
        file_hash=file_hash(clip),
    )
    project.save_analysis(analysis)
    sb = Storyboard(title="T", sections=[StoryboardSection(title="S", segments=[
        StoryboardSegment(clip_path=clip.resolve(), in_point=0.0, out_point=2.0, include=True),
    ])])
    project.save_storyboard(sb)
    return tmp_path


def test_tighten_dry_run_does_not_modify(tmp_path):
    root = _setup(tmp_path)
    result = runner.invoke(app, ["tighten", "--path", str(root), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Tightened" in result.output
    # storyboard still has the single original segment
    sb = Project(root).load_storyboard()
    assert len(sb.sections[0].segments) == 1


def test_tighten_modifies_storyboard(tmp_path):
    root = _setup(tmp_path)
    result = runner.invoke(app, ["tighten", "--path", str(root)])
    assert result.exit_code == 0, result.output
    sb = Project(root).load_storyboard()
    # "um" filler removed -> segment split into two
    segs = sb.sections[0].segments
    assert len(segs) == 2
    assert segs[0].out_point < segs[1].in_point


def test_tighten_requires_storyboard(tmp_path):
    project = Project(tmp_path)
    project.init()
    result = runner.invoke(app, ["tighten", "--path", str(tmp_path)])
    assert result.exit_code == 1
    assert "storyboard" in result.output.lower()
