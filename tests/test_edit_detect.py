"""Tests for vlogkit.edit.detect — cut-range detectors (TDD)."""

from __future__ import annotations

from vlogkit.edit.detect import (
    detect_dead_air,
    detect_filler_words,
    detect_word_gap_silence,
    normalize_token,
)
from vlogkit.models import TranscriptSegment, WordTimestamp


def _seg(words: list[WordTimestamp], confidence: float = 1.0) -> TranscriptSegment:
    start = words[0].start if words else 0.0
    end = words[-1].end if words else 0.0
    text = " ".join(w.word for w in words)
    return TranscriptSegment(
        start=start, end=end, text=text, confidence=confidence, words=words
    )


# ---------------------------------------------------------------------------
# normalize_token
# ---------------------------------------------------------------------------


def test_normalize_lowercases():
    assert normalize_token("UH") == "uh"


def test_normalize_strips_surrounding_punctuation_and_whitespace():
    assert normalize_token(" Um,") == "um"
    assert normalize_token(" ah ") == "ah"
    assert normalize_token("well?") == "well"
    assert normalize_token('"hello"') == "hello"
    assert normalize_token("'kay-") == "kay"


def test_normalize_keeps_internal_characters():
    assert normalize_token("you-know") == "you-know"
    assert normalize_token("don't.") == "don't"


# ---------------------------------------------------------------------------
# detect_filler_words
# ---------------------------------------------------------------------------


def test_filler_match_is_case_and_punctuation_insensitive():
    seg = _seg(
        [
            WordTimestamp(start=0.0, end=0.3, word="Um,"),
            WordTimestamp(start=0.3, end=0.6, word="UH"),
            WordTimestamp(start=0.6, end=0.9, word=" ah "),
        ]
    )
    cuts = detect_filler_words([seg], ["um", "uh", "ah"])
    assert cuts == [(0.0, 0.3), (0.3, 0.6), (0.6, 0.9)]


def test_filler_ignores_non_filler_words():
    seg = _seg(
        [
            WordTimestamp(start=0.0, end=0.5, word="hello"),
            WordTimestamp(start=0.5, end=0.8, word="um"),
            WordTimestamp(start=0.8, end=1.2, word="world"),
        ]
    )
    cuts = detect_filler_words([seg], ["um"])
    assert cuts == [(0.5, 0.8)]


def test_filler_filters_are_normalized_too():
    seg = _seg([WordTimestamp(start=0.0, end=0.3, word="um")])
    # filler entry has caps/punctuation but should still match
    cuts = detect_filler_words([seg], ["UM!"])
    assert cuts == [(0.0, 0.3)]


def test_filler_phrase_across_two_words():
    seg = _seg(
        [
            WordTimestamp(start=0.0, end=0.4, word="I"),
            WordTimestamp(start=0.4, end=0.7, word="you"),
            WordTimestamp(start=0.7, end=1.0, word="know"),
            WordTimestamp(start=1.0, end=1.4, word="right"),
        ]
    )
    cuts = detect_filler_words([seg], ["you know"])
    assert cuts == [(0.4, 1.0)]


def test_filler_phrase_and_single_combined():
    seg = _seg(
        [
            WordTimestamp(start=0.0, end=0.3, word="um"),
            WordTimestamp(start=0.3, end=0.6, word="you"),
            WordTimestamp(start=0.6, end=0.9, word="know"),
        ]
    )
    cuts = detect_filler_words([seg], ["um", "you know"])
    # single "um" cut, plus the phrase cut
    assert (0.0, 0.3) in cuts
    assert (0.3, 0.9) in cuts


def test_filler_empty_transcript():
    assert detect_filler_words([], ["um"]) == []


def test_filler_skips_words_with_bad_timing():
    seg = _seg(
        [
            WordTimestamp(start=1.0, end=1.0, word="um"),  # end <= start
            WordTimestamp(start=2.0, end=1.5, word="uh"),  # end < start
            WordTimestamp(start=3.0, end=3.4, word="ah"),  # ok
        ]
    )
    cuts = detect_filler_words([seg], ["um", "uh", "ah"])
    assert cuts == [(3.0, 3.4)]


def test_filler_flattens_multiple_segments_in_order():
    seg1 = _seg([WordTimestamp(start=0.0, end=0.3, word="um")])
    seg2 = _seg([WordTimestamp(start=5.0, end=5.3, word="uh")])
    cuts = detect_filler_words([seg1, seg2], ["um", "uh"])
    assert cuts == [(0.0, 0.3), (5.0, 5.3)]


# ---------------------------------------------------------------------------
# detect_word_gap_silence
# ---------------------------------------------------------------------------


def test_word_gap_emits_only_gaps_at_or_above_threshold():
    seg = _seg(
        [
            WordTimestamp(start=0.0, end=1.0, word="a"),
            WordTimestamp(start=1.2, end=2.0, word="b"),  # gap 0.2 -> skip
            WordTimestamp(start=3.0, end=3.5, word="c"),  # gap 1.0 -> keep
        ]
    )
    cuts = detect_word_gap_silence([seg], min_silence=0.5)
    assert cuts == [(2.0, 3.0)]


def test_word_gap_uses_prev_end_next_start():
    seg = _seg(
        [
            WordTimestamp(start=0.0, end=1.0, word="a"),
            WordTimestamp(start=2.5, end=3.0, word="b"),
        ]
    )
    cuts = detect_word_gap_silence([seg], min_silence=1.0)
    assert cuts == [(1.0, 2.5)]


def test_word_gap_flattens_across_segments_in_time_order():
    # Segments deliberately out of time order to confirm sorting
    seg_late = _seg([WordTimestamp(start=10.0, end=10.5, word="late")])
    seg_early = _seg(
        [
            WordTimestamp(start=0.0, end=1.0, word="x"),
            WordTimestamp(start=1.1, end=2.0, word="y"),
        ]
    )
    cuts = detect_word_gap_silence([seg_late, seg_early], min_silence=1.0)
    # gap from y.end(2.0) -> late.start(10.0); the 0.1 gap inside seg_early is dropped
    assert cuts == [(2.0, 10.0)]


def test_word_gap_empty_transcript():
    assert detect_word_gap_silence([], min_silence=0.5) == []


def test_word_gap_single_word_no_gap():
    seg = _seg([WordTimestamp(start=0.0, end=1.0, word="solo")])
    assert detect_word_gap_silence([seg], min_silence=0.1) == []


# ---------------------------------------------------------------------------
# detect_dead_air
# ---------------------------------------------------------------------------


def test_dead_air_filters_by_duration():
    silences = [(0.0, 0.4), (1.0, 3.0), (5.0, 5.2)]
    cuts = detect_dead_air(silences, min_silence=0.5)
    assert cuts == [(1.0, 3.0)]


def test_dead_air_applies_symmetric_padding():
    silences = [(1.0, 3.0)]
    cuts = detect_dead_air(silences, min_silence=0.5, pad=0.25)
    assert cuts == [(1.25, 2.75)]


def test_dead_air_drops_over_padded_tiny_silences():
    # duration 0.6 passes the min_silence gate but pad of 0.4 each side
    # would leave (1.4, 1.2) -> non-positive length -> dropped
    silences = [(1.0, 1.6)]
    cuts = detect_dead_air(silences, min_silence=0.5, pad=0.4)
    assert cuts == []


def test_dead_air_no_pad_returns_passing_ranges_unchanged():
    silences = [(2.0, 4.0)]
    assert detect_dead_air(silences, min_silence=1.0) == [(2.0, 4.0)]


def test_dead_air_empty():
    assert detect_dead_air([], min_silence=0.5) == []
