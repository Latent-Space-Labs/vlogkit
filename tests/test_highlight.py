"""Tests for vlogkit.repurpose.highlight — scene selection + montage assembly."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from vlogkit.config import Settings
from vlogkit.models import (
    ClipAnalysis,
    ClipMetadata,
    MurchScore,
    SceneSegment,
    Storyboard,
)
from vlogkit.project import Project
from vlogkit.repurpose.highlight import (
    build_highlight_storyboard,
    make_highlight,
    select_highlight_scenes,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _murch(composite: float) -> MurchScore:
    return MurchScore(
        scene_type="aesthetic",
        aesthetic=composite,
        credibility=composite,
        impact=composite,
        memorability=composite,
        fun=composite,
        composite=composite,
    )


def _scene(start: float, end: float, composite: float | None) -> SceneSegment:
    return SceneSegment(
        start=start,
        end=end,
        murch=_murch(composite) if composite is not None else None,
    )


def _analysis(path: str, scenes: list[SceneSegment], *, resolution=(320, 240), fps=30.0) -> ClipAnalysis:
    return ClipAnalysis(
        metadata=ClipMetadata(
            filename=Path(path).name,
            path=Path(path),
            duration=999.0,
            resolution=resolution,
            fps=fps,
            file_size=1234,
        ),
        scenes=scenes,
    )


# ---------------------------------------------------------------------------
# select_highlight_scenes
# ---------------------------------------------------------------------------


def test_select_empty_no_analyses():
    assert select_highlight_scenes([]) == []


def test_select_no_scenes_returns_empty():
    a = _analysis("a.mp4", [])
    assert select_highlight_scenes([a]) == []


def test_select_greedy_by_score():
    # three scenes, each 5s; budget 12s -> pick the two highest scores.
    a = _analysis(
        "a.mp4",
        [
            _scene(0.0, 5.0, 10.0),   # low
            _scene(5.0, 10.0, 90.0),  # high
            _scene(10.0, 15.0, 50.0), # mid
        ],
    )
    picked = select_highlight_scenes([a], max_duration=12.0, order="score")
    scores = [s[3] for s in picked]
    # highest two selected: 90 then 50 (descending order)
    assert scores == [90.0, 50.0]


def test_select_respects_duration_cap():
    a = _analysis(
        "a.mp4",
        [
            _scene(0.0, 5.0, 90.0),
            _scene(5.0, 10.0, 80.0),
            _scene(10.0, 15.0, 70.0),
        ],
    )
    picked = select_highlight_scenes([a], max_duration=11.0, order="score")
    total = sum(e - s for (_p, s, e, _sc) in picked)
    assert total <= 11.0
    # only the first 5s scene fits after... 5+5=10 <=11, +5=15 >11, so two scenes.
    assert len(picked) == 2
    assert total == 10.0


def test_select_skips_too_long_keeps_smaller():
    # highest-scored scene is too long for remaining budget; a smaller lower
    # scored scene should still be picked.
    a = _analysis(
        "a.mp4",
        [
            _scene(0.0, 10.0, 99.0),  # 10s, too long for budget 6
            _scene(10.0, 13.0, 50.0),  # 3s fits
            _scene(13.0, 15.0, 40.0),  # 2s fits
        ],
    )
    picked = select_highlight_scenes([a], max_duration=6.0, order="score")
    total = sum(e - s for (_p, s, e, _sc) in picked)
    assert total <= 6.0
    scores = [s[3] for s in picked]
    # the 99 scene is skipped (too long); 50 then 40 selected
    assert scores == [50.0, 40.0]


def test_select_chronological_order():
    a = _analysis(
        "a.mp4",
        [
            _scene(10.0, 12.0, 50.0),
            _scene(0.0, 2.0, 90.0),
            _scene(5.0, 7.0, 70.0),
        ],
    )
    picked = select_highlight_scenes([a], max_duration=60.0, order="chronological")
    starts = [s[1] for s in picked]
    assert starts == [0.0, 5.0, 10.0]


def test_select_chronological_order_across_clips():
    a = _analysis("b.mp4", [_scene(0.0, 2.0, 50.0)])
    b = _analysis("a.mp4", [_scene(0.0, 2.0, 90.0)])
    picked = select_highlight_scenes([a, b], max_duration=60.0, order="chronological")
    # sorted by (clip_path, start) -> a.mp4 before b.mp4
    paths = [str(s[0]) for s in picked]
    assert paths == ["a.mp4", "b.mp4"]


def test_select_unscored_fallback_by_time():
    # No murch scores anywhere -> all score 0.0, still selects up to budget.
    a = _analysis(
        "a.mp4",
        [
            _scene(0.0, 2.0, None),
            _scene(2.0, 4.0, None),
            _scene(4.0, 6.0, None),
        ],
    )
    picked = select_highlight_scenes([a], max_duration=5.0, order="chronological")
    total = sum(e - s for (_p, s, e, _sc) in picked)
    assert total <= 5.0
    assert len(picked) == 2
    assert all(s[3] == 0.0 for s in picked)


def test_select_returns_tuples_shape():
    a = _analysis("a.mp4", [_scene(1.0, 3.0, 42.0)])
    picked = select_highlight_scenes([a], max_duration=60.0)
    assert len(picked) == 1
    clip_path, start, end, score = picked[0]
    assert isinstance(clip_path, Path)
    assert (start, end, score) == (1.0, 3.0, 42.0)


# ---------------------------------------------------------------------------
# build_highlight_storyboard
# ---------------------------------------------------------------------------


def test_build_storyboard_one_section_per_scene():
    scenes = [
        (Path("a.mp4"), 0.0, 2.0, 90.0),
        (Path("b.mp4"), 1.0, 3.0, 50.0),
    ]
    sb = build_highlight_storyboard(scenes, title="My Reel")
    assert isinstance(sb, Storyboard)
    assert sb.title == "My Reel"
    assert len(sb.sections) == 1
    segs = sb.sections[0].segments
    assert len(segs) == 2
    assert segs[0].clip_path == Path("a.mp4")
    assert segs[0].in_point == 0.0
    assert segs[0].out_point == 2.0
    assert segs[0].include is True
    assert segs[1].clip_path == Path("b.mp4")
    assert segs[1].in_point == 1.0
    assert segs[1].out_point == 3.0


def test_build_storyboard_empty():
    sb = build_highlight_storyboard([])
    assert len(sb.sections) == 1
    assert sb.sections[0].segments == []


# ---------------------------------------------------------------------------
# make_highlight — unit (no scenes raises)
# ---------------------------------------------------------------------------


def test_make_highlight_no_scenes_raises(tmp_path):
    proj = Project(tmp_path, settings=Settings())
    proj.cache_dir.mkdir(parents=True, exist_ok=True)
    # No analyses cached -> load_all_analyses returns [] -> no scenes.
    with pytest.raises(RuntimeError):
        make_highlight(proj)


# ---------------------------------------------------------------------------
# make_highlight — real end-to-end with ffmpeg
# ---------------------------------------------------------------------------


def _ffmpeg_bin() -> str | None:
    full = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
    if Path(full).exists():
        return full
    return shutil.which("ffmpeg")


def _ffprobe_duration(path: Path, ffmpeg_bin: str) -> float:
    ffprobe = ffmpeg_bin.replace("ffmpeg", "ffprobe")
    if not Path(ffprobe).exists() and shutil.which("ffprobe") is None:
        pytest.skip("ffprobe not available")
    if not Path(ffprobe).exists():
        ffprobe = shutil.which("ffprobe")
    out = subprocess.run(
        [
            ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def _make_testsrc(path: Path, ffmpeg_bin: str, dur: float = 4.0) -> None:
    cmd = [
        ffmpeg_bin,
        "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=30:duration={dur}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}",
        "-shortest", "-pix_fmt", "yuv420p", "-y", str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.mark.skipif(_ffmpeg_bin() is None, reason="ffmpeg not installed")
def test_make_highlight_end_to_end(tmp_path):
    ffmpeg_bin = _ffmpeg_bin()
    clip1 = tmp_path / "one.mp4"
    clip2 = tmp_path / "two.mp4"
    _make_testsrc(clip1, ffmpeg_bin, 4.0)
    _make_testsrc(clip2, ffmpeg_bin, 4.0)

    proj = Project(tmp_path, settings=Settings())
    proj.cache_dir.mkdir(parents=True, exist_ok=True)

    # Two scenes per clip, scored. Each scene 2s. Budget 4s -> two highest scenes.
    a1 = ClipAnalysis(
        metadata=ClipMetadata(
            filename="one.mp4", path=clip1, duration=4.0,
            resolution=(320, 240), fps=30.0, file_size=clip1.stat().st_size,
            creation_time=datetime(2024, 1, 1),
        ),
        scenes=[_scene(0.0, 2.0, 95.0), _scene(2.0, 4.0, 20.0)],
        file_hash="",
    )
    a2 = ClipAnalysis(
        metadata=ClipMetadata(
            filename="two.mp4", path=clip2, duration=4.0,
            resolution=(320, 240), fps=30.0, file_size=clip2.stat().st_size,
            creation_time=datetime(2024, 1, 2),
        ),
        scenes=[_scene(0.0, 2.0, 80.0), _scene(2.0, 4.0, 10.0)],
        file_hash="",
    )
    # Fix file_hash to match on-disk so load_analysis accepts the cache.
    from vlogkit.project import file_hash as _fh
    a1.file_hash = _fh(clip1)
    a2.file_hash = _fh(clip2)
    proj.save_analysis(a1)
    proj.save_analysis(a2)

    out = make_highlight(proj, max_duration=4.0, ffmpeg_bin=ffmpeg_bin)
    assert out.exists()
    assert out.stat().st_size > 0
    assert out == proj.cache_dir / "highlight.mp4"

    dur = _ffprobe_duration(out, ffmpeg_bin)
    # two 2s scenes ~= 4s; allow encoding slack.
    assert dur <= 4.6
