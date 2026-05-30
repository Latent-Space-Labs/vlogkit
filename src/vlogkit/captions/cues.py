"""Group timed words into readable caption cues and remap them onto the
final concatenated storyboard timeline.

Two pure functions:

* :func:`group_words_into_cues` — turn a flat list of timeline-relative
  :class:`WordTimestamp` objects into wrapped, duration-bounded
  :class:`CaptionCue` objects following BBC/Netflix subtitle conventions.
* :func:`build_cues` — walk an included storyboard, remap each segment's
  transcript words onto the final timeline, and feed them through
  :func:`group_words_into_cues`.

Both functions are side-effect free and never touch the filesystem.
"""

from __future__ import annotations

from pathlib import Path

from vlogkit.models import (
    CaptionCue,
    CaptionStyle,
    ClipAnalysis,
    Storyboard,
    WordTimestamp,
)

# Gap (seconds) between consecutive words that we treat as a natural
# pause / sentence boundary and therefore a good place to start a new cue.
_PAUSE_GAP = 0.6


def _clean(word: str) -> str:
    """Whisper words often carry a leading space; normalise to a bare token."""
    return word.strip()


def _wrap(tokens: list[str], style: CaptionStyle) -> str | None:
    """Greedy word-wrap ``tokens`` into at most ``style.max_lines`` lines, each
    no wider than ``style.max_chars_per_line``.

    Returns the wrapped string (lines joined with ``"\\n"``), or ``None`` if the
    tokens cannot fit within the line/length budget.
    """
    max_chars = style.max_chars_per_line
    max_lines = style.max_lines

    lines: list[str] = []
    current = ""
    for tok in tokens:
        # A single token longer than a line can never fit cleanly.
        if len(tok) > max_chars:
            if current:
                lines.append(current)
                current = ""
            lines.append(tok)  # overflow line; let caller decide via budget
            continue
        candidate = f"{current} {tok}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = tok
    if current:
        lines.append(current)

    if len(lines) > max_lines:
        return None
    if any(len(line) > max_chars for line in lines):
        return None
    return "\n".join(lines)


def _flush(group: list[WordTimestamp], style: CaptionStyle) -> CaptionCue:
    tokens = [_clean(w.word) for w in group]
    wrapped = _wrap(tokens, style)
    if wrapped is None:
        # Fallback: a single oversized token must still produce a cue rather
        # than silently dropping words.
        wrapped = " ".join(tokens)
    return CaptionCue(
        start=group[0].start,
        end=group[-1].end,
        text=wrapped,
        words=list(group),
    )


def group_words_into_cues(
    words: list[WordTimestamp], style: CaptionStyle
) -> list[CaptionCue]:
    """Group a flat list of timeline-relative words into caption cues.

    A new cue is started when adding the next word would:

    * exceed the wrap budget (``max_lines`` lines of ``max_chars_per_line``), or
    * push the cue duration (last end - first start) past ``style.max_duration``, or
    * follow a large pause gap (``>= _PAUSE_GAP`` seconds) — a natural break.

    Additionally, once a word ends with sentence punctuation (``. ! ?``) the
    cue is closed so the next sentence begins a fresh cue.
    """
    if not words:
        return []

    cues: list[CaptionCue] = []
    group: list[WordTimestamp] = []
    sentence_break_pending = False

    for word in words:
        if not group:
            group.append(word)
            sentence_break_pending = _clean(word.word).endswith((".", "!", "?"))
            continue

        prev = group[-1]
        gap = word.start - prev.end
        candidate = group + [word]
        candidate_tokens = [_clean(w.word) for w in candidate]
        duration = word.end - group[0].start

        too_long = _wrap(candidate_tokens, style) is None
        too_slow = duration > style.max_duration
        big_pause = gap >= _PAUSE_GAP

        if too_long or too_slow or big_pause or sentence_break_pending:
            cues.append(_flush(group, style))
            group = [word]
        else:
            group.append(word)

        sentence_break_pending = _clean(word.word).endswith((".", "!", "?"))

    if group:
        cues.append(_flush(group, style))
    return cues


def _build_lookup(
    analyses: list[ClipAnalysis] | dict,
) -> dict[str, ClipAnalysis]:
    """Map clip path / name -> ClipAnalysis.

    Accepts a pre-built dict (returned as-is) or a list of analyses, keyed by
    both the resolved absolute path and the bare filename as a fallback.
    """
    if isinstance(analyses, dict):
        return analyses

    lookup: dict[str, ClipAnalysis] = {}
    for a in analyses:
        resolved = str(a.metadata.path.resolve())
        lookup.setdefault(resolved, a)
        lookup.setdefault(a.metadata.path.name, a)
    return lookup


def _resolve_analysis(
    clip_path: Path, lookup: dict[str, ClipAnalysis]
) -> ClipAnalysis | None:
    # Match by resolved absolute path first, then by bare filename.
    for key in (str(clip_path.resolve()), str(clip_path), clip_path.name):
        if key in lookup:
            return lookup[key]
    return None


def _all_words(analysis: ClipAnalysis) -> list[WordTimestamp]:
    out: list[WordTimestamp] = []
    for seg in analysis.transcript:
        out.extend(seg.words)
    return out


def build_cues(
    storyboard: Storyboard,
    analyses: list[ClipAnalysis] | dict,
    style: CaptionStyle | None = None,
) -> list[CaptionCue]:
    """Remap each included segment's transcript words onto the final timeline
    and group them into caption cues.

    ``offset`` accumulates the duration of prior *included* segments, so cue
    timestamps are expressed against the final concatenated render.
    """
    if style is None:
        style = CaptionStyle()

    lookup = _build_lookup(analyses)
    cues: list[CaptionCue] = []
    offset = 0.0

    for section in storyboard.sections:
        for seg in section.segments:
            if not seg.include:
                continue

            in_point = seg.in_point
            out_point = seg.out_point
            window = out_point - in_point

            analysis = _resolve_analysis(seg.clip_path, lookup)
            if analysis is not None:
                source_words = _all_words(analysis)
                remapped: list[WordTimestamp] = []
                for word in source_words:
                    # Skip words fully outside the segment window.
                    if word.end <= in_point or word.start >= out_point:
                        continue
                    new_start = max(word.start, in_point) - in_point + offset
                    new_end = min(word.end, out_point) - in_point + offset
                    remapped.append(
                        WordTimestamp(
                            word=word.word,
                            start=new_start,
                            end=new_end,
                            confidence=word.confidence,
                        )
                    )
                cues.extend(group_words_into_cues(remapped, style))

            # Advance the timeline by this included segment's duration even when
            # it had no usable transcript, so later segments stay aligned.
            offset += window

    return cues
