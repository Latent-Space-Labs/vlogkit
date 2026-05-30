"""Tests for the B-roll / cutaway suggestion engine.

Written test-first (TDD). Exercises three pure functions:

* ``find_talking_stretches`` — detect narration-heavy spans on the final timeline.
* ``rank_broll_scenes`` — order candidate scenes by aesthetic score.
* ``suggest_broll`` — assemble :class:`BrollSuggestion` objects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vlogkit.edit.broll import (
    BrollSuggestion,
    find_talking_stretches,
    rank_broll_scenes,
    suggest_broll,
)
from vlogkit.models import (
    ClipAnalysis,
    ClipMetadata,
    MurchScore,
    SceneSegment,
    Storyboard,
    StoryboardSection,
    StoryboardSegment,
    TranscriptSegment,
)


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def _meta(path: str, duration: float = 60.0) -> ClipMetadata:
    return ClipMetadata(
        filename=Path(path).name,
        path=Path(path),
        duration=duration,
        resolution=(1920, 1080),
        fps=30.0,
        file_size=1000,
    )


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


def _scene(start: float, end: float, aesthetic: float | None) -> SceneSegment:
    return SceneSegment(
        start=start,
        end=end,
        description="scene",
        tags=[],
        murch=_murch(aesthetic) if aesthetic is not None else None,
    )


def _ts(start: float, end: float, text: str) -> TranscriptSegment:
    return TranscriptSegment(start=start, end=end, text=text)


def _analysis(
    path: str,
    transcript: list[TranscriptSegment] | None = None,
    scenes: list[SceneSegment] | None = None,
    duration: float = 60.0,
) -> ClipAnalysis:
    return ClipAnalysis(
        metadata=_meta(path, duration),
        transcript=transcript or [],
        scenes=scenes or [],
    )


def _segment(clip: str, in_point: float, out_point: float, include: bool = True) -> StoryboardSegment:
    return StoryboardSegment(
        clip_path=Path(clip), in_point=in_point, out_point=out_point, include=include
    )


def _board(*segments: StoryboardSegment) -> Storyboard:
    return Storyboard(sections=[StoryboardSection(title="main", segments=list(segments))])


# --------------------------------------------------------------------------- #
# find_talking_stretches
# --------------------------------------------------------------------------- #
def test_talking_stretch_basic_single_segment():
    a = _analysis(
        "/clips/a.mp4",
        transcript=[_ts(2.0, 8.0, "hello there this is narration")],
    )
    # Segment spans 0..10 of clip a; whole window has transcript -> one stretch.
    board = _board(_segment("/clips/a.mp4", 0.0, 10.0))
    stretches = find_talking_stretches(board, [a], min_len=4.0)

    assert len(stretches) == 1
    start, end, text = stretches[0]
    assert start == pytest.approx(0.0)
    assert end == pytest.approx(10.0)
    assert "narration" in text


def test_talking_stretch_respects_min_len():
    a = _analysis("/clips/a.mp4", transcript=[_ts(0.5, 2.0, "short")])
    # Window only 3s long < min_len 4.0 -> dropped.
    board = _board(_segment("/clips/a.mp4", 0.0, 3.0))
    assert find_talking_stretches(board, [a], min_len=4.0) == []


def test_talking_stretch_no_transcript_in_window():
    # Transcript exists but lies entirely outside the segment window.
    a = _analysis("/clips/a.mp4", transcript=[_ts(40.0, 45.0, "later words")])
    board = _board(_segment("/clips/a.mp4", 0.0, 10.0))
    assert find_talking_stretches(board, [a], min_len=4.0) == []


def test_talking_stretch_remaps_to_final_timeline():
    a = _analysis("/clips/a.mp4", transcript=[_ts(2.0, 8.0, "first clip talking")])
    b = _analysis("/clips/b.mp4", transcript=[_ts(1.0, 9.0, "second clip talking")])
    # First included segment: clip a 0..10 -> timeline 0..10 (offset 0).
    # Second included segment: clip b 5..15 -> timeline 10..20 (offset 10).
    board = _board(
        _segment("/clips/a.mp4", 0.0, 10.0),
        _segment("/clips/b.mp4", 5.0, 15.0),
    )
    stretches = find_talking_stretches(board, [a, b], min_len=4.0)
    assert len(stretches) == 2
    assert stretches[0][0] == pytest.approx(0.0)
    assert stretches[0][1] == pytest.approx(10.0)
    assert stretches[1][0] == pytest.approx(10.0)
    assert stretches[1][1] == pytest.approx(20.0)
    assert "second" in stretches[1][2]


def test_talking_stretch_skips_excluded_segments_but_keeps_offset():
    a = _analysis("/clips/a.mp4", transcript=[_ts(0.0, 9.0, "kept talking")])
    b = _analysis("/clips/b.mp4", transcript=[_ts(0.0, 9.0, "dropped talking")])
    c = _analysis("/clips/c.mp4", transcript=[_ts(0.0, 9.0, "after talking")])
    board = _board(
        _segment("/clips/a.mp4", 0.0, 10.0),
        _segment("/clips/b.mp4", 0.0, 10.0, include=False),
        _segment("/clips/c.mp4", 0.0, 10.0),
    )
    stretches = find_talking_stretches(board, [a, b, c], min_len=4.0)
    assert len(stretches) == 2
    # Excluded segment must NOT advance the offset (mirrors caption cue builder).
    assert stretches[0][0] == pytest.approx(0.0)
    assert stretches[1][0] == pytest.approx(10.0)
    assert "after" in stretches[1][2]


def test_talking_stretch_match_by_filename():
    # Analysis path differs in directory, matched by .name fallback.
    a = _analysis("/elsewhere/a.mp4", transcript=[_ts(1.0, 9.0, "talking")])
    board = _board(_segment("a.mp4", 0.0, 10.0))
    stretches = find_talking_stretches(board, [a], min_len=4.0)
    assert len(stretches) == 1


# --------------------------------------------------------------------------- #
# rank_broll_scenes
# --------------------------------------------------------------------------- #
def test_rank_orders_by_aesthetic_desc():
    a = _analysis(
        "/clips/a.mp4",
        scenes=[_scene(0.0, 3.0, 20.0), _scene(3.0, 6.0, 90.0)],
    )
    b = _analysis("/clips/b.mp4", scenes=[_scene(0.0, 3.0, 50.0)])
    ranked = rank_broll_scenes([a, b])
    aesthetics = [r[3] for r in ranked]
    assert aesthetics == [90.0, 50.0, 20.0]
    # Tuple shape: (clip_path, start, end, aesthetic)
    assert ranked[0][0] == Path("/clips/a.mp4")
    assert ranked[0][1] == pytest.approx(3.0)
    assert ranked[0][2] == pytest.approx(6.0)


def test_rank_treats_missing_murch_as_zero():
    a = _analysis("/clips/a.mp4", scenes=[_scene(0.0, 3.0, None), _scene(3.0, 6.0, 10.0)])
    ranked = rank_broll_scenes([a])
    assert ranked[0][3] == 10.0
    assert ranked[-1][3] == 0.0


def test_rank_excludes_clip():
    a = _analysis("/clips/a.mp4", scenes=[_scene(0.0, 3.0, 90.0)])
    b = _analysis("/clips/b.mp4", scenes=[_scene(0.0, 3.0, 50.0)])
    ranked = rank_broll_scenes([a, b], exclude_clip=Path("/clips/a.mp4"))
    assert all(r[0] != Path("/clips/a.mp4") for r in ranked)
    assert len(ranked) == 1
    assert ranked[0][0] == Path("/clips/b.mp4")


def test_rank_top_n():
    a = _analysis(
        "/clips/a.mp4",
        scenes=[_scene(i, i + 1, float(i)) for i in range(10)],
    )
    ranked = rank_broll_scenes([a], top_n=3)
    assert len(ranked) == 3
    assert [r[3] for r in ranked] == [9.0, 8.0, 7.0]


def test_rank_empty():
    assert rank_broll_scenes([]) == []
    assert rank_broll_scenes([_analysis("/clips/a.mp4")]) == []


# --------------------------------------------------------------------------- #
# suggest_broll
# --------------------------------------------------------------------------- #
def _talking_clip(path: str) -> ClipAnalysis:
    # A talking-head clip: plenty of transcript, no pretty scenes.
    return _analysis(path, transcript=[_ts(0.0, 30.0, "lots of narration here over time")])


def _broll_clip(path: str, aesthetic: float, n: int = 1) -> ClipAnalysis:
    scenes = [_scene(i * 5.0, i * 5.0 + 5.0, aesthetic - i) for i in range(n)]
    return _analysis(path, scenes=scenes)


def test_suggest_basic():
    talk = _talking_clip("/clips/talk.mp4")
    broll = _broll_clip("/clips/pretty.mp4", 90.0, n=1)
    board = _board(_segment("/clips/talk.mp4", 0.0, 20.0))

    suggestions = suggest_broll(board, [talk, broll], max_suggestions=5, min_stretch=4.0)
    assert len(suggestions) == 1
    s = suggestions[0]
    assert isinstance(s, BrollSuggestion)
    # Cutaway falls within the talking stretch (timeline 0..20).
    assert 0.0 <= s.timeline_start < s.timeline_end <= 20.0
    assert s.source_clip == "/clips/pretty.mp4"
    assert s.source_start == pytest.approx(0.0)
    assert s.source_end == pytest.approx(5.0)
    assert s.score == 90.0
    assert s.trigger_text
    assert s.reason
    # Cutaway length capped at 5s and the scene length.
    assert s.timeline_end - s.timeline_start == pytest.approx(5.0)
    assert s.source_end - s.source_start == pytest.approx(5.0)


def test_suggest_does_not_reuse_same_scene():
    talk1 = _talking_clip("/clips/talk1.mp4")
    talk2 = _talking_clip("/clips/talk2.mp4")
    # Two distinct aesthetic scenes available.
    broll = _broll_clip("/clips/pretty.mp4", 90.0, n=2)
    board = _board(
        _segment("/clips/talk1.mp4", 0.0, 20.0),
        _segment("/clips/talk2.mp4", 0.0, 20.0),
    )
    suggestions = suggest_broll(board, [talk1, talk2, broll], max_suggestions=5)
    assert len(suggestions) == 2
    used = {(s.source_clip, s.source_start, s.source_end) for s in suggestions}
    assert len(used) == 2  # no scene reused


def test_suggest_respects_max_suggestions():
    talks = [_talking_clip(f"/clips/talk{i}.mp4") for i in range(5)]
    broll = _broll_clip("/clips/pretty.mp4", 90.0, n=10)
    board = _board(*[_segment(f"/clips/talk{i}.mp4", 0.0, 20.0) for i in range(5)])
    suggestions = suggest_broll(board, talks + [broll], max_suggestions=2)
    assert len(suggestions) == 2


def test_suggest_skips_short_source_scenes():
    talk = _talking_clip("/clips/talk.mp4")
    # Only scene is 1.5s long -> below the ~2s minimum cutaway source.
    broll = _analysis("/clips/pretty.mp4", scenes=[_scene(0.0, 1.5, 90.0)])
    board = _board(_segment("/clips/talk.mp4", 0.0, 20.0))
    assert suggest_broll(board, [talk, broll]) == []


def test_suggest_empty_when_no_transcript():
    # No talking stretches anywhere.
    broll = _broll_clip("/clips/pretty.mp4", 90.0, n=2)
    board = _board(_segment("/clips/pretty.mp4", 0.0, 20.0))
    assert suggest_broll(board, [broll]) == []


def test_suggest_empty_when_no_scored_scenes():
    talk = _talking_clip("/clips/talk.mp4")
    board = _board(_segment("/clips/talk.mp4", 0.0, 20.0))
    # No aesthetic scenes at all.
    assert suggest_broll(board, [talk]) == []


def test_suggest_longest_stretch_first():
    # A short stretch and a long stretch; the long one should be served first
    # (and thus get the highest-aesthetic scene).
    short = _analysis("/clips/short.mp4", transcript=[_ts(0.0, 5.0, "short talk")])
    long = _analysis("/clips/long.mp4", transcript=[_ts(0.0, 18.0, "long talk")])
    broll = _broll_clip("/clips/pretty.mp4", 90.0, n=2)  # scenes 90 and 89
    board = _board(
        _segment("/clips/short.mp4", 0.0, 5.0),
        _segment("/clips/long.mp4", 0.0, 18.0),
    )
    suggestions = suggest_broll(board, [short, long, broll], max_suggestions=5)
    assert len(suggestions) == 2
    # The suggestion landing in the long stretch (timeline >= 5) gets aesthetic 90.
    by_score = sorted(suggestions, key=lambda s: -s.score)
    assert by_score[0].score == 90.0
    assert by_score[0].timeline_start >= 5.0


def test_suggest_cutaway_within_stretch_bounds():
    talk = _analysis("/clips/talk.mp4", transcript=[_ts(0.0, 8.0, "narration words")])
    broll = _broll_clip("/clips/pretty.mp4", 90.0, n=1)
    board = _board(_segment("/clips/talk.mp4", 0.0, 8.0))
    suggestions = suggest_broll(board, [talk, broll], min_stretch=4.0)
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.timeline_start >= 0.0
    assert s.timeline_end <= 8.0
