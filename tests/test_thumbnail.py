"""Tests for vlogkit.repurpose.thumbnail (TDD)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from vlogkit.config import Settings
from vlogkit.ffmpeg_util import resolve_ffmpeg
from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
from vlogkit.project import Project, file_hash
from vlogkit.repurpose.thumbnail import (
    build_thumbnail_command,
    has_drawtext,
    make_thumbnails,
    rank_thumbnail_candidates,
)

FFMPEG_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"


def _murch(aesthetic: float) -> MurchScore:
    return MurchScore(
        scene_type="aesthetic",
        aesthetic=aesthetic,
        credibility=0.0,
        impact=0.0,
        memorability=0.0,
        fun=0.0,
        composite=0.0,
    )


def _analysis(path: str, scenes: list[SceneSegment]) -> ClipAnalysis:
    return ClipAnalysis(
        metadata=ClipMetadata(
            filename=Path(path).name,
            path=Path(path),
            duration=10.0,
            resolution=(1920, 1080),
            fps=30.0,
            file_size=1234,
        ),
        scenes=scenes,
    )


# --- rank_thumbnail_candidates ---------------------------------------------


def test_rank_empty_returns_empty():
    assert rank_thumbnail_candidates([]) == []


def test_rank_orders_by_aesthetic_desc():
    a = _analysis(
        "/clips/a.mp4",
        [
            SceneSegment(start=0.0, end=2.0, murch=_murch(10.0)),
            SceneSegment(start=2.0, end=4.0, murch=_murch(90.0)),
            SceneSegment(start=4.0, end=6.0, murch=_murch(50.0)),
        ],
    )
    result = rank_thumbnail_candidates([a], top_n=3)
    scores = [score for _, _, score in result]
    assert scores == [90.0, 50.0, 10.0]


def test_rank_top_n_truncates():
    a = _analysis(
        "/clips/a.mp4",
        [
            SceneSegment(start=0.0, end=2.0, murch=_murch(10.0)),
            SceneSegment(start=2.0, end=4.0, murch=_murch(90.0)),
            SceneSegment(start=4.0, end=6.0, murch=_murch(50.0)),
        ],
    )
    result = rank_thumbnail_candidates([a], top_n=2)
    assert len(result) == 2
    assert [s for _, _, s in result] == [90.0, 50.0]


def test_rank_uses_midpoint_timestamp():
    a = _analysis("/clips/a.mp4", [SceneSegment(start=2.0, end=8.0, murch=_murch(5.0))])
    (clip_path, timestamp, score) = rank_thumbnail_candidates([a])[0]
    assert clip_path == Path("/clips/a.mp4")
    assert timestamp == pytest.approx(5.0)
    assert score == pytest.approx(5.0)


def test_rank_none_murch_scores_zero():
    a = _analysis(
        "/clips/a.mp4",
        [
            SceneSegment(start=0.0, end=2.0, murch=None),
            SceneSegment(start=2.0, end=4.0, murch=_murch(30.0)),
        ],
    )
    result = rank_thumbnail_candidates([a], top_n=2)
    assert [s for _, _, s in result] == [30.0, 0.0]


def test_rank_spans_multiple_clips():
    a = _analysis("/clips/a.mp4", [SceneSegment(start=0.0, end=2.0, murch=_murch(20.0))])
    b = _analysis("/clips/b.mp4", [SceneSegment(start=0.0, end=2.0, murch=_murch(80.0))])
    result = rank_thumbnail_candidates([a, b], top_n=2)
    assert result[0][0] == Path("/clips/b.mp4")
    assert result[1][0] == Path("/clips/a.mp4")


# --- build_thumbnail_command ------------------------------------------------


def test_build_command_basic_no_title():
    cmd = build_thumbnail_command(
        Path("/clips/a.mp4"), 5.0, Path("/out/thumb.jpg")
    )
    assert "-ss" in cmd
    ss_idx = cmd.index("-ss")
    assert cmd[ss_idx + 1] == "5.0"
    # seek before input
    assert cmd.index("-ss") < cmd.index("-i")
    assert cmd[cmd.index("-i") + 1] == "/clips/a.mp4"
    assert "-frames:v" in cmd
    assert cmd[cmd.index("-frames:v") + 1] == "1"
    # scale/crop filter present
    vf = cmd[cmd.index("-vf") + 1]
    assert "scale=1280:720:force_original_aspect_ratio=increase" in vf
    assert "crop=1280:720" in vf
    assert "drawtext" not in vf
    assert "-y" in cmd
    assert cmd[-1] == "/out/thumb.jpg"


def test_build_command_resolution_applied():
    cmd = build_thumbnail_command(
        Path("/clips/a.mp4"), 1.0, Path("/out/t.jpg"), resolution=(1080, 1920)
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert "scale=1080:1920:force_original_aspect_ratio=increase" in vf
    assert "crop=1080:1920" in vf


def test_build_command_with_title_adds_drawtext():
    cmd = build_thumbnail_command(
        Path("/clips/a.mp4"), 2.0, Path("/out/t.jpg"), title="My Vlog", font_size=72
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert "drawtext=" in vf
    assert "text='My Vlog'" in vf
    assert "fontcolor=white" in vf
    assert "fontsize=72" in vf
    assert "borderw=4" in vf
    assert "bordercolor=black" in vf
    assert "x=(w-text_w)/2" in vf
    assert "y=h-text_h-60" in vf


def test_build_command_uses_ffmpeg_bin():
    cmd = build_thumbnail_command(
        Path("/clips/a.mp4"), 0.0, Path("/out/t.jpg"), ffmpeg_bin="/custom/ffmpeg"
    )
    assert cmd[0] == "/custom/ffmpeg"


def test_build_command_escapes_title():
    cmd = build_thumbnail_command(
        Path("/clips/a.mp4"),
        0.0,
        Path("/out/t.jpg"),
        title="Day 1: it's here 50% off",
    )
    vf = cmd[cmd.index("-vf") + 1]
    # colon escaped
    assert r"\:" in vf
    # apostrophe escaped
    assert r"\'" in vf
    # percent escaped
    assert r"\%" in vf
    # raw unescaped colon should not appear inside the drawtext text payload
    assert "Day 1: it" not in vf


def test_build_command_escapes_backslash():
    cmd = build_thumbnail_command(
        Path("/clips/a.mp4"), 0.0, Path("/out/t.jpg"), title="a\\b"
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert r"a\\b" in vf


# --- make_thumbnails (E2E) --------------------------------------------------


def test_make_thumbnails_raises_without_candidates(tmp_path):
    settings = Settings()
    project = Project(tmp_path, settings=settings)
    project.cache_dir.mkdir(parents=True, exist_ok=True)
    with pytest.raises(RuntimeError):
        make_thumbnails(project, ffmpeg_bin=FFMPEG_FULL if os.path.exists(FFMPEG_FULL) else "ffmpeg")


def _ffmpeg_for_e2e() -> str | None:
    if os.path.exists(FFMPEG_FULL):
        return FFMPEG_FULL
    return resolve_ffmpeg(None)


def _ffmpeg_available(bin_: str | None) -> bool:
    if not bin_:
        return False
    try:
        subprocess.run([bin_, "-version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


@pytest.mark.skipif(
    not _ffmpeg_available(_ffmpeg_for_e2e()), reason="ffmpeg not available"
)
def test_make_thumbnails_e2e(tmp_path):
    ffmpeg_bin = _ffmpeg_for_e2e()
    clip = tmp_path / "clip.mp4"
    subprocess.run(
        [
            ffmpeg_bin,
            "-f", "lavfi",
            "-i", "testsrc=duration=3:size=320x240:rate=30",
            "-pix_fmt", "yuv420p",
            "-y", str(clip),
        ],
        capture_output=True,
        check=True,
    )

    settings = Settings()
    project = Project(tmp_path, settings=settings)

    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename=clip.name,
            path=clip,
            duration=3.0,
            resolution=(320, 240),
            fps=30.0,
            file_size=clip.stat().st_size,
        ),
        scenes=[SceneSegment(start=0.0, end=2.0, murch=_murch(75.0))],
        file_hash=file_hash(clip),
    )
    # Ensure load_all_analyses returns our analysis (hash must match).
    project.save_analysis(analysis)

    out = make_thumbnails(project, count=1, title=None, ffmpeg_bin=ffmpeg_bin)
    assert len(out) == 1
    assert out[0].exists()
    assert out[0].stat().st_size > 0
    assert out[0].suffix == ".jpg"


@pytest.mark.skipif(
    not _ffmpeg_available(_ffmpeg_for_e2e()), reason="ffmpeg not available"
)
def test_make_thumbnails_e2e_with_title(tmp_path):
    ffmpeg_bin = _ffmpeg_for_e2e()
    if not has_drawtext(ffmpeg_bin):
        pytest.skip("ffmpeg lacks drawtext (no freetype)")

    clip = tmp_path / "clip.mp4"
    subprocess.run(
        [
            ffmpeg_bin,
            "-f", "lavfi",
            "-i", "testsrc=duration=3:size=320x240:rate=30",
            "-pix_fmt", "yuv420p",
            "-y", str(clip),
        ],
        capture_output=True,
        check=True,
    )

    settings = Settings()
    project = Project(tmp_path, settings=settings)
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename=clip.name,
            path=clip,
            duration=3.0,
            resolution=(320, 240),
            fps=30.0,
            file_size=clip.stat().st_size,
        ),
        scenes=[SceneSegment(start=0.0, end=2.0, murch=_murch(75.0))],
        file_hash=file_hash(clip),
    )
    project.save_analysis(analysis)

    out = make_thumbnails(project, count=1, title="Hello: it's me", ffmpeg_bin=ffmpeg_bin)
    assert len(out) == 1
    assert out[0].exists()
    assert out[0].stat().st_size > 0
