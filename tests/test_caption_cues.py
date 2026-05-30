"""Tests for vlogkit.captions.cues — word grouping and timeline remapping."""

from __future__ import annotations

from pathlib import Path

import pytest

from vlogkit.captions.cues import build_cues, group_words_into_cues
from vlogkit.models import (
    CaptionStyle,
    ClipAnalysis,
    ClipMetadata,
    Storyboard,
    StoryboardSection,
    StoryboardSegment,
    TranscriptSegment,
    WordTimestamp,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def w(word: str, start: float, end: float, confidence: float = 1.0) -> WordTimestamp:
    return WordTimestamp(word=word, start=start, end=end, confidence=confidence)


def words_from_spec(spec, *, dt: float = 0.4, gap: float = 0.0, t0: float = 0.0):
    """Build evenly-spaced words from a list of (word) strings."""
    out = []
    t = t0
    for token in spec:
        out.append(w(token, t, t + dt))
        t += dt + gap
    return out


def meta(name: str, path: str | None = None) -> ClipMetadata:
    return ClipMetadata(
        filename=name,
        path=Path(path or f"/clips/{name}").resolve(),
        duration=60.0,
        resolution=(1920, 1080),
        fps=30.0,
        file_size=1000,
    )


def analysis(name: str, words: list[WordTimestamp], path: str | None = None) -> ClipAnalysis:
    seg = TranscriptSegment(
        start=words[0].start if words else 0.0,
        end=words[-1].end if words else 0.0,
        text=" ".join(x.word for x in words),
        words=list(words),
    )
    return ClipAnalysis(metadata=meta(name, path), transcript=[seg] if words else [])


# --------------------------------------------------------------------------- #
# group_words_into_cues
# --------------------------------------------------------------------------- #
def test_empty_input_returns_empty_list():
    assert group_words_into_cues([], CaptionStyle()) == []


def test_simple_short_phrase_is_one_cue():
    words = words_from_spec(["hello", "there", "world"])
    cues = group_words_into_cues(words, CaptionStyle())
    assert len(cues) == 1
    cue = cues[0]
    assert cue.text == "hello there world"
    assert cue.start == words[0].start
    assert cue.end == words[-1].end
    assert [x.word for x in cue.words] == ["hello", "there", "world"]


def test_words_with_leading_whitespace_are_stripped():
    # whisper emits leading spaces on words
    words = [w(" hello", 0.0, 0.4), w(" world", 0.4, 0.8)]
    cues = group_words_into_cues(words, CaptionStyle())
    assert len(cues) == 1
    assert cues[0].text == "hello world"


def test_wraps_to_multiple_lines_within_single_cue():
    style = CaptionStyle(max_chars_per_line=12, max_lines=2)
    # "hello world" = 11 chars (fits line 1); adding "again" -> wrap to line 2
    words = words_from_spec(["hello", "world", "again"])
    cues = group_words_into_cues(words, style)
    assert len(cues) == 1
    assert cues[0].text == "hello world\nagain"
    # each line within limit
    for line in cues[0].text.split("\n"):
        assert len(line) <= style.max_chars_per_line


def test_splits_into_new_cue_when_capacity_exceeded():
    # capacity = max_lines * max_chars = 2 * 5 = 10 chars-ish; force a split
    style = CaptionStyle(max_chars_per_line=5, max_lines=1, max_duration=100.0)
    words = words_from_spec(["aaaaa", "bbbbb", "ccccc"])
    cues = group_words_into_cues(words, style)
    # Each word is 5 chars and only 1 line of 5 chars fits -> one word per cue
    assert len(cues) == 3
    assert [c.text for c in cues] == ["aaaaa", "bbbbb", "ccccc"]


def test_splits_when_duration_exceeds_max_duration():
    style = CaptionStyle(max_chars_per_line=100, max_lines=2, max_duration=1.0)
    # words back to back, 0.4s each. After ~3 words duration would exceed 1.0s
    words = words_from_spec(["a", "b", "c", "d", "e"], dt=0.4, gap=0.0)
    cues = group_words_into_cues(words, style)
    assert len(cues) >= 2
    for cue in cues:
        assert cue.end - cue.start <= style.max_duration + 1e-9


def test_splits_on_large_pause_gap():
    style = CaptionStyle(max_chars_per_line=100, max_lines=2, max_duration=100.0)
    first = words_from_spec(["hello", "world"], dt=0.3, gap=0.0, t0=0.0)
    # large gap (>=0.6s) before the next group
    second = words_from_spec(["new", "sentence"], dt=0.3, gap=0.0, t0=first[-1].end + 0.8)
    cues = group_words_into_cues(first + second, style)
    assert len(cues) == 2
    assert cues[0].text == "hello world"
    assert cues[1].text == "new sentence"


def test_prefers_break_after_sentence_punctuation():
    # No hard limits hit; but a sentence ends mid-stream. We expect the next
    # cue to start fresh after the period rather than running on.
    style = CaptionStyle(max_chars_per_line=18, max_lines=1, max_duration=100.0)
    words = [
        w("Hello", 0.0, 0.4),
        w("world.", 0.4, 0.8),
        w("Next", 0.9, 1.3),
        w("one", 1.3, 1.7),
    ]
    cues = group_words_into_cues(words, style)
    assert cues[0].text == "Hello world."
    assert cues[1].text == "Next one"


def test_sentence_break_does_not_lose_words():
    style = CaptionStyle(max_chars_per_line=42, max_lines=2, max_duration=100.0)
    words = [
        w("One.", 0.0, 0.4),
        w("Two.", 0.4, 0.8),
        w("Three", 0.8, 1.2),
    ]
    cues = group_words_into_cues(words, style)
    joined = " ".join(c.text.replace("\n", " ") for c in cues)
    assert joined == "One. Two. Three"


# --------------------------------------------------------------------------- #
# build_cues
# --------------------------------------------------------------------------- #
def test_build_cues_single_segment_offset_zero():
    words = words_from_spec(["hello", "world"], dt=0.5, gap=0.0, t0=2.0)
    a = analysis("clip1.mp4", words)
    sb = Storyboard(
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    StoryboardSegment(
                        clip_path=a.metadata.path, in_point=2.0, out_point=3.0
                    )
                ],
            )
        ]
    )
    cues = build_cues(sb, [a])
    assert len(cues) == 1
    # words started at t=2.0 in clip, in_point=2.0, offset=0 -> remapped to 0.0
    assert cues[0].start == pytest.approx(0.0)
    assert cues[0].end == pytest.approx(1.0)
    assert cues[0].text == "hello world"


def test_build_cues_multi_segment_cumulative_offset():
    words1 = words_from_spec(["aa", "bb"], dt=0.5, gap=0.0, t0=0.0)  # 0..1
    words2 = words_from_spec(["cc", "dd"], dt=0.5, gap=0.0, t0=0.0)  # 0..1
    a1 = analysis("a.mp4", words1)
    a2 = analysis("b.mp4", words2)
    sb = Storyboard(
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    StoryboardSegment(clip_path=a1.metadata.path, in_point=0.0, out_point=1.0),
                    StoryboardSegment(clip_path=a2.metadata.path, in_point=0.0, out_point=1.0),
                ],
            )
        ]
    )
    cues = build_cues(sb, [a1, a2])
    assert len(cues) == 2
    # second segment offset = 1.0 (duration of first segment)
    assert cues[0].start == pytest.approx(0.0)
    assert cues[1].start == pytest.approx(1.0)
    assert cues[1].end == pytest.approx(2.0)
    assert cues[0].text == "aa bb"
    assert cues[1].text == "cc dd"


def test_build_cues_excluded_segments_skipped():
    words1 = words_from_spec(["keep", "this"], dt=0.5, gap=0.0, t0=0.0)
    words2 = words_from_spec(["drop", "that"], dt=0.5, gap=0.0, t0=0.0)
    words3 = words_from_spec(["also", "keep"], dt=0.5, gap=0.0, t0=0.0)
    a1 = analysis("a.mp4", words1)
    a2 = analysis("b.mp4", words2)
    a3 = analysis("c.mp4", words3)
    sb = Storyboard(
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    StoryboardSegment(clip_path=a1.metadata.path, in_point=0.0, out_point=1.0),
                    StoryboardSegment(clip_path=a2.metadata.path, in_point=0.0, out_point=1.0, include=False),
                    StoryboardSegment(clip_path=a3.metadata.path, in_point=0.0, out_point=1.0),
                ],
            )
        ]
    )
    cues = build_cues(sb, [a1, a2, a3])
    texts = [c.text for c in cues]
    assert texts == ["keep this", "also keep"]
    # excluded segment must not advance the offset
    assert cues[1].start == pytest.approx(1.0)


def test_build_cues_trims_words_outside_in_out():
    # word at 0..0.5 is before in_point; word at 3..3.5 is after out_point
    words = [
        w("before", 0.0, 0.5),
        w("inside", 1.2, 1.6),
        w("after", 3.0, 3.5),
    ]
    a = analysis("clip.mp4", words)
    sb = Storyboard(
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    StoryboardSegment(clip_path=a.metadata.path, in_point=1.0, out_point=2.0)
                ],
            )
        ]
    )
    cues = build_cues(sb, [a])
    assert len(cues) == 1
    assert cues[0].text == "inside"
    # remapped: 1.2 - 1.0 + 0 = 0.2
    assert cues[0].start == pytest.approx(0.2)
    assert cues[0].end == pytest.approx(0.6)


def test_build_cues_clamps_partially_overlapping_word():
    # word spans the in_point boundary
    words = [w("spanning", 0.5, 1.5)]
    a = analysis("clip.mp4", words)
    sb = Storyboard(
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    StoryboardSegment(clip_path=a.metadata.path, in_point=1.0, out_point=2.0)
                ],
            )
        ]
    )
    cues = build_cues(sb, [a])
    assert len(cues) == 1
    # start clamped to in_point (1.0) -> remapped 0.0; end 1.5 -> 0.5
    assert cues[0].start == pytest.approx(0.0)
    assert cues[0].end == pytest.approx(0.5)


def test_build_cues_matches_clip_by_bare_filename():
    words = words_from_spec(["matched", "byname"], dt=0.5, gap=0.0, t0=0.0)
    a = analysis("myclip.mp4", words, path="/some/abs/myclip.mp4")
    sb = Storyboard(
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    # bare filename, not the absolute path stored in analysis
                    StoryboardSegment(clip_path=Path("myclip.mp4"), in_point=0.0, out_point=1.0)
                ],
            )
        ]
    )
    cues = build_cues(sb, [a])
    assert len(cues) == 1
    assert cues[0].text == "matched byname"


def test_build_cues_missing_analysis_handled_gracefully():
    sb = Storyboard(
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    StoryboardSegment(clip_path=Path("/clips/ghost.mp4"), in_point=0.0, out_point=1.0)
                ],
            )
        ]
    )
    # no analyses at all -> no crash, empty result
    assert build_cues(sb, []) == []


def test_build_cues_clip_without_word_timestamps_skipped():
    a = analysis("clip.mp4", [])  # no transcript / words
    sb = Storyboard(
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    StoryboardSegment(clip_path=a.metadata.path, in_point=0.0, out_point=1.0)
                ],
            )
        ]
    )
    assert build_cues(sb, [a]) == []


def test_build_cues_accepts_prebuilt_dict():
    words = words_from_spec(["dict", "lookup"], dt=0.5, gap=0.0, t0=0.0)
    a = analysis("clip.mp4", words)
    sb = Storyboard(
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    StoryboardSegment(clip_path=Path("clip.mp4"), in_point=0.0, out_point=1.0)
                ],
            )
        ]
    )
    lookup = {"clip.mp4": a}
    cues = build_cues(sb, lookup)
    assert len(cues) == 1
    assert cues[0].text == "dict lookup"


def test_build_cues_default_style_when_none():
    words = words_from_spec(["default", "style"], dt=0.5, gap=0.0, t0=0.0)
    a = analysis("clip.mp4", words)
    sb = Storyboard(
        sections=[
            StoryboardSection(
                title="s",
                segments=[
                    StoryboardSegment(clip_path=a.metadata.path, in_point=0.0, out_point=1.0)
                ],
            )
        ]
    )
    cues = build_cues(sb, [a], style=None)
    assert len(cues) == 1
    assert cues[0].text == "default style"
