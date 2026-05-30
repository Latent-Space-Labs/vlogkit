"""Pure interval math over ``(start, end)`` float tuples in seconds.

No domain knowledge, no models, no vlogkit imports. Every function treats
intervals as half-open-ish ranges where ``end <= start`` means "empty" and is
dropped or normalized away.
"""

from __future__ import annotations

Interval = tuple[float, float]


def merge_intervals(
    intervals: list[Interval], gap: float = 0.0
) -> list[Interval]:
    """Sort by start and merge overlapping or near-adjacent intervals.

    Two intervals are merged when ``next.start <= current.end + gap`` (so
    touching intervals merge at the default ``gap=0.0``). Zero-or-negative
    length inputs (``end <= start``) are dropped. The result is sorted and
    non-overlapping. Empty input -> ``[]``.
    """
    # Drop zero/negative-length intervals up front.
    valid = [(s, e) for (s, e) in intervals if e > s]
    if not valid:
        return []

    valid.sort(key=lambda iv: iv[0])

    merged: list[Interval] = [valid[0]]
    for start, end in valid[1:]:
        cur_start, cur_end = merged[-1]
        if start <= cur_end + gap:
            merged[-1] = (cur_start, max(cur_end, end))
        else:
            merged.append((start, end))
    return merged


def clamp_intervals(
    intervals: list[Interval], window: Interval
) -> list[Interval]:
    """Clip each interval to ``window``, preserving order.

    Intervals lying entirely outside the window, or that collapse to
    zero-length once clipped, are dropped.
    """
    w0, w1 = window
    result: list[Interval] = []
    for start, end in intervals:
        clipped_start = max(start, w0)
        clipped_end = min(end, w1)
        if clipped_end > clipped_start:
            result.append((clipped_start, clipped_end))
    return result


def invert_intervals(
    window: Interval, cuts: list[Interval]
) -> list[Interval]:
    """Return the "keep" ranges = ``window`` minus ``cuts``.

    The cuts are merged, clamped to the window, and the gaps between them
    within ``[w0, w1]`` are returned. With no (effective) cuts the whole
    window is kept (when ``w1 > w0``, else ``[]``). Cuts fully covering the
    window yield ``[]``. A middle cut splits the window into two keep ranges.
    """
    w0, w1 = window
    if w1 <= w0:
        return []

    # Merge first (collapses overlaps/adjacency, drops empties), then clamp to
    # the window so partial-overlap cuts are trimmed to the window edges.
    cleaned = clamp_intervals(merge_intervals(cuts), window)
    if not cleaned:
        return [(w0, w1)]

    keep: list[Interval] = []
    cursor = w0
    for cut_start, cut_end in cleaned:
        if cut_start > cursor:
            keep.append((cursor, cut_start))
        cursor = max(cursor, cut_end)
    if cursor < w1:
        keep.append((cursor, w1))
    return keep


def total_duration(intervals: list[Interval]) -> float:
    """Sum of ``end - start`` over the intervals.

    Merges first so overlapping ranges are not double-counted and
    zero/negative-length entries are ignored.
    """
    return sum(end - start for start, end in merge_intervals(intervals))


def filter_min_length(
    intervals: list[Interval], min_length: float
) -> list[Interval]:
    """Drop intervals shorter than ``min_length`` (exact match is kept)."""
    return [(s, e) for (s, e) in intervals if (e - s) >= min_length]
