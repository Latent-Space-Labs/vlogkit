"""Tests for tighten_storyboard — silence + filler auto-cut over a storyboard."""

from pathlib import Path

from vlogkit.edit.tighten import collect_cuts, tighten_storyboard
from vlogkit.models import (
    AudioAnalysis,
    ClipAnalysis,
    ClipMetadata,
    Storyboard,
    StoryboardSection,
    StoryboardSegment,
    TightenConfig,
    TranscriptSegment,
    WordTimestamp,
)


def _analysis(path: Path, words, silences=None) -> ClipAnalysis:
    return ClipAnalysis(
        metadata=ClipMetadata(
            filename=path.name, path=path, duration=30.0,
            resolution=(1920, 1080), fps=30.0, file_size=1,
        ),
        transcript=[TranscriptSegment(
            start=words[0][0], end=words[-1][1], text=" ".join(w[2] for w in words),
            words=[WordTimestamp(start=s, end=e, word=w) for s, e, w in words],
        )] if words else [],
        audio=AudioAnalysis(silence_segments=silences or []),
    )


def _sb(path: Path, in_p=0.0, out_p=10.0) -> Storyboard:
    return Storyboard(title="T", sections=[StoryboardSection(title="S", segments=[
        StoryboardSegment(clip_path=path, in_point=in_p, out_point=out_p, include=True),
    ])])


def test_collect_cuts_finds_fillers_and_gaps():
    p = Path("/tmp/a.mp4")
    a = _analysis(p, [
        (0.0, 0.5, "Hello"),
        (0.6, 0.9, "um"),       # filler
        (1.0, 1.4, "world"),
        (3.0, 3.4, "again"),    # 1.6s gap before this -> silence cut
    ])
    cuts = collect_cuts(a, (0.0, 10.0), TightenConfig(min_silence=0.6))
    # filler "um" (0.6-0.9) and the gap (1.4-3.0) should both be present, merged/sorted
    assert any(abs(s - 0.6) < 1e-6 and abs(e - 0.9) < 1e-6 for s, e in cuts)
    assert any(abs(s - 1.4) < 1e-6 and abs(e - 3.0) < 1e-6 for s, e in cuts)


def test_tighten_removes_filler_and_shortens_duration(tmp_path):
    p = tmp_path / "a.mp4"
    p.touch()
    a = _analysis(p, [
        (0.0, 0.5, "Hello"),
        (0.6, 0.9, "um"),
        (1.0, 1.5, "world"),
    ])
    sb = _sb(p, 0.0, 1.5)
    tightened, stats = tighten_storyboard(sb, [a], TightenConfig(remove_silence=False))
    segs = tightened.sections[0].segments
    # The "um" interval (0.6-0.9) is cut, splitting into two keep ranges.
    assert len(segs) == 2
    assert segs[0].in_point == 0.0 and abs(segs[0].out_point - 0.6) < 1e-6
    assert abs(segs[1].in_point - 0.9) < 1e-6 and abs(segs[1].out_point - 1.5) < 1e-6
    assert stats.tightened_duration < stats.original_duration
    assert abs(stats.removed_duration - 0.3) < 1e-6


def test_tighten_drops_microcuts_below_min_keep(tmp_path):
    p = tmp_path / "a.mp4"
    p.touch()
    # Two fillers bracket a 0.2s sliver of speech -> that sliver is below min_keep
    # and gets dropped; only the substantial trailing range survives.
    a = _analysis(p, [
        (0.0, 0.5, "um"),       # filler
        (0.5, 0.7, "ok"),       # 0.2s keep sliver (< min_keep)
        (0.7, 1.0, "uh"),       # filler
        (1.0, 2.0, "content"),  # substantial keep
    ])
    sb = _sb(p, 0.0, 2.0)
    tightened, _ = tighten_storyboard(sb, [a], TightenConfig(remove_silence=False, min_keep=0.3))
    segs = tightened.sections[0].segments
    # only the substantial keep range survives
    assert len(segs) == 1
    assert abs(segs[0].in_point - 1.0) < 1e-6


def test_tighten_passes_through_excluded_and_unanalyzed(tmp_path):
    p = tmp_path / "a.mp4"
    q = tmp_path / "b.mp4"
    p.touch()
    q.touch()
    a = _analysis(p, [(0.0, 0.3, "um"), (0.4, 2.0, "hi")])
    sb = Storyboard(title="T", sections=[StoryboardSection(title="S", segments=[
        StoryboardSegment(clip_path=p, in_point=0.0, out_point=2.0, include=False),  # excluded
        StoryboardSegment(clip_path=q, in_point=0.0, out_point=2.0, include=True),   # no analysis
    ])])
    tightened, _ = tighten_storyboard(sb, [a], TightenConfig())
    segs = tightened.sections[0].segments
    # excluded passes untouched; unanalyzed clip passes untouched
    assert any(not s.include and s.clip_path == p for s in segs)
    assert any(s.clip_path == q and s.in_point == 0.0 and s.out_point == 2.0 for s in segs)


def test_tighten_keeps_segment_when_everything_cut(tmp_path):
    """Safety: if tightening would erase the whole segment, keep it as-is."""
    p = tmp_path / "a.mp4"
    p.touch()
    a = _analysis(p, [(0.0, 2.0, "um")])  # the entire window is a filler
    sb = _sb(p, 0.0, 2.0)
    tightened, _ = tighten_storyboard(sb, [a], TightenConfig(remove_silence=False))
    segs = tightened.sections[0].segments
    assert len(segs) == 1
    assert segs[0].in_point == 0.0 and segs[0].out_point == 2.0
