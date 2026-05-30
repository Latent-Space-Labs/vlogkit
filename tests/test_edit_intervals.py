"""Tests for pure interval math used by the auto-cut feature."""

import pytest

from vlogkit.edit.intervals import (
    clamp_intervals,
    filter_min_length,
    invert_intervals,
    merge_intervals,
    total_duration,
)


# ---------------------------------------------------------------------------
# merge_intervals
# ---------------------------------------------------------------------------


def test_merge_empty():
    assert merge_intervals([]) == []


def test_merge_single():
    assert merge_intervals([(1.0, 2.0)]) == [(1.0, 2.0)]


def test_merge_overlapping():
    assert merge_intervals([(0.0, 2.0), (1.0, 3.0)]) == [(0.0, 3.0)]


def test_merge_nested():
    assert merge_intervals([(0.0, 5.0), (1.0, 2.0)]) == [(0.0, 5.0)]


def test_merge_touching():
    # next.start == current.end -> merge (touching, gap defaults to 0)
    assert merge_intervals([(0.0, 2.0), (2.0, 4.0)]) == [(0.0, 4.0)]


def test_merge_disjoint():
    assert merge_intervals([(0.0, 1.0), (2.0, 3.0)]) == [(0.0, 1.0), (2.0, 3.0)]


def test_merge_unsorted():
    assert merge_intervals([(5.0, 6.0), (0.0, 1.0), (2.0, 3.0)]) == [
        (0.0, 1.0),
        (2.0, 3.0),
        (5.0, 6.0),
    ]


def test_merge_unsorted_overlapping():
    assert merge_intervals([(2.0, 4.0), (0.0, 2.5), (3.5, 5.0)]) == [(0.0, 5.0)]


def test_merge_gap_bridged():
    # gap of 1.0 bridges intervals 0.5 apart
    assert merge_intervals([(0.0, 1.0), (1.5, 2.0)], gap=1.0) == [(0.0, 2.0)]


def test_merge_gap_not_bridged():
    # gap of 0.4 does NOT bridge intervals 0.5 apart
    assert merge_intervals([(0.0, 1.0), (1.5, 2.0)], gap=0.4) == [
        (0.0, 1.0),
        (1.5, 2.0),
    ]


def test_merge_gap_exact_boundary():
    # next.start == current.end + gap -> merge (<= boundary is inclusive)
    assert merge_intervals([(0.0, 1.0), (1.5, 2.0)], gap=0.5) == [(0.0, 2.0)]


def test_merge_drops_zero_length():
    assert merge_intervals([(1.0, 1.0)]) == []


def test_merge_drops_negative_length():
    assert merge_intervals([(3.0, 1.0)]) == []


def test_merge_drops_zero_length_among_valid():
    assert merge_intervals([(0.0, 1.0), (2.0, 2.0), (3.0, 4.0)]) == [
        (0.0, 1.0),
        (3.0, 4.0),
    ]


def test_merge_result_non_overlapping_and_sorted():
    result = merge_intervals([(10.0, 12.0), (0.0, 1.0), (0.5, 3.0), (11.0, 15.0)])
    assert result == [(0.0, 3.0), (10.0, 15.0)]
    # verify sorted and non-overlapping
    for (a_start, a_end), (b_start, b_end) in zip(result, result[1:]):
        assert a_start <= a_end
        assert a_end < b_start


# ---------------------------------------------------------------------------
# clamp_intervals
# ---------------------------------------------------------------------------


def test_clamp_inside_unchanged():
    assert clamp_intervals([(2.0, 4.0)], (0.0, 10.0)) == [(2.0, 4.0)]


def test_clamp_drops_entirely_outside_left():
    assert clamp_intervals([(-5.0, -1.0)], (0.0, 10.0)) == []


def test_clamp_drops_entirely_outside_right():
    assert clamp_intervals([(11.0, 15.0)], (0.0, 10.0)) == []


def test_clamp_clips_left_edge():
    assert clamp_intervals([(-2.0, 3.0)], (0.0, 10.0)) == [(0.0, 3.0)]


def test_clamp_clips_right_edge():
    assert clamp_intervals([(8.0, 14.0)], (0.0, 10.0)) == [(8.0, 10.0)]


def test_clamp_clips_both_edges():
    assert clamp_intervals([(-3.0, 14.0)], (0.0, 10.0)) == [(0.0, 10.0)]


def test_clamp_drops_zero_length_after_clip():
    # touches the window edge but has no length inside it
    assert clamp_intervals([(-2.0, 0.0)], (0.0, 10.0)) == []
    assert clamp_intervals([(10.0, 12.0)], (0.0, 10.0)) == []


def test_clamp_multiple():
    assert clamp_intervals(
        [(-1.0, 2.0), (5.0, 6.0), (20.0, 30.0)], (0.0, 10.0)
    ) == [(0.0, 2.0), (5.0, 6.0)]


# ---------------------------------------------------------------------------
# invert_intervals
# ---------------------------------------------------------------------------


def test_invert_no_cuts():
    assert invert_intervals((0.0, 10.0), []) == [(0.0, 10.0)]


def test_invert_no_cuts_empty_window():
    assert invert_intervals((5.0, 5.0), []) == []
    assert invert_intervals((5.0, 3.0), []) == []


def test_invert_middle_cut_splits():
    assert invert_intervals((0.0, 10.0), [(4.0, 6.0)]) == [(0.0, 4.0), (6.0, 10.0)]


def test_invert_two_middle_cuts():
    assert invert_intervals((0.0, 10.0), [(2.0, 3.0), (6.0, 7.0)]) == [
        (0.0, 2.0),
        (3.0, 6.0),
        (7.0, 10.0),
    ]


def test_invert_cut_at_left_edge():
    assert invert_intervals((0.0, 10.0), [(0.0, 3.0)]) == [(3.0, 10.0)]


def test_invert_cut_at_right_edge():
    assert invert_intervals((0.0, 10.0), [(7.0, 10.0)]) == [(0.0, 7.0)]


def test_invert_cut_extends_beyond_left():
    # cut starts before the window -> clamped to window start
    assert invert_intervals((0.0, 10.0), [(-5.0, 3.0)]) == [(3.0, 10.0)]


def test_invert_cut_extends_beyond_right():
    assert invert_intervals((0.0, 10.0), [(7.0, 20.0)]) == [(0.0, 7.0)]


def test_invert_cut_extends_beyond_both():
    assert invert_intervals((0.0, 10.0), [(-5.0, 20.0)]) == []


def test_invert_full_cover_exact():
    assert invert_intervals((0.0, 10.0), [(0.0, 10.0)]) == []


def test_invert_cut_entirely_outside_window():
    # cuts that don't touch the window leave it fully intact
    assert invert_intervals((0.0, 10.0), [(20.0, 30.0)]) == [(0.0, 10.0)]


def test_invert_overlapping_cuts_merged_first():
    # overlapping cuts should be merged, producing one keep gap
    assert invert_intervals((0.0, 10.0), [(2.0, 5.0), (4.0, 7.0)]) == [
        (0.0, 2.0),
        (7.0, 10.0),
    ]


def test_invert_adjacent_cuts_no_zero_length_gap():
    # touching cuts must not produce a zero-length keep between them
    assert invert_intervals((0.0, 10.0), [(2.0, 5.0), (5.0, 8.0)]) == [
        (0.0, 2.0),
        (8.0, 10.0),
    ]


def test_invert_empty_window_with_cuts():
    assert invert_intervals((5.0, 5.0), [(1.0, 6.0)]) == []


# ---------------------------------------------------------------------------
# total_duration
# ---------------------------------------------------------------------------


def test_total_duration_empty():
    assert total_duration([]) == pytest.approx(0.0)


def test_total_duration_disjoint():
    assert total_duration([(0.0, 2.0), (5.0, 8.0)]) == pytest.approx(5.0)


def test_total_duration_overlapping_counts_once():
    # overlapping intervals must be merged so overlap is not double-counted
    assert total_duration([(0.0, 3.0), (2.0, 5.0)]) == pytest.approx(5.0)


def test_total_duration_ignores_zero_length():
    assert total_duration([(0.0, 2.0), (3.0, 3.0)]) == pytest.approx(2.0)


def test_total_duration_fractional():
    assert total_duration([(0.0, 1.5), (2.25, 3.0)]) == pytest.approx(2.25)


# ---------------------------------------------------------------------------
# filter_min_length
# ---------------------------------------------------------------------------


def test_filter_min_length_drops_short():
    assert filter_min_length([(0.0, 0.5), (1.0, 5.0)], 1.0) == [(1.0, 5.0)]


def test_filter_min_length_keeps_exact_boundary():
    # interval exactly == min_length is kept
    assert filter_min_length([(0.0, 1.0)], 1.0) == [(0.0, 1.0)]


def test_filter_min_length_drops_just_under():
    assert filter_min_length([(0.0, 0.999)], 1.0) == []


def test_filter_min_length_empty():
    assert filter_min_length([], 1.0) == []


def test_filter_min_length_all_kept():
    assert filter_min_length([(0.0, 2.0), (3.0, 6.0)], 1.0) == [
        (0.0, 2.0),
        (3.0, 6.0),
    ]
