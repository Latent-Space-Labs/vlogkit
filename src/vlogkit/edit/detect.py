"""Cut-range detectors for the auto-cut feature.

Each detector returns a list of ``(start, end)`` float tuples in seconds
representing CUT ranges — the time to REMOVE. Ranges are returned raw and
unmerged; merging/inverting is handled by a separate module.
"""

from __future__ import annotations

from vlogkit.models import TranscriptSegment, WordTimestamp

# Characters stripped from the surrounding edges of a token.
_STRIP_CHARS = ".,!?;:\"'- \t\n"


def normalize_token(word: str) -> str:
    """Lowercase and strip surrounding whitespace/punctuation from a token.

    Internal characters are preserved, e.g. ``" Um,"`` -> ``"um"`` and
    ``"you-know"`` -> ``"you-know"``.
    """
    return word.strip().strip(_STRIP_CHARS).lower()


def _flatten_words(transcript: list[TranscriptSegment]) -> list[WordTimestamp]:
    """Flatten all words across segments into a single time-sorted list."""
    words: list[WordTimestamp] = []
    for segment in transcript:
        words.extend(segment.words)
    words.sort(key=lambda w: (w.start, w.end))
    return words


def detect_filler_words(
    transcript: list[TranscriptSegment], fillers: list[str]
) -> list[tuple[float, float]]:
    """Emit cut ranges for words/phrases matching the filler list.

    Matching is case- and punctuation-insensitive via :func:`normalize_token`.
    Single-token fillers match individual words. Filler entries containing a
    space are matched against a sliding window of consecutive words, emitting
    ``(first_word.start, last_word.end)``. Words with no usable timing
    (``end <= start``) are skipped. Order is preserved.
    """
    words = _flatten_words(transcript)
    norm = [normalize_token(w.word) for w in words]

    single_fillers: set[str] = set()
    phrase_fillers: list[list[str]] = []
    for entry in fillers:
        tokens = [normalize_token(t) for t in entry.split() if normalize_token(t)]
        if not tokens:
            continue
        if len(tokens) == 1:
            single_fillers.add(tokens[0])
        else:
            phrase_fillers.append(tokens)

    cuts: list[tuple[float, float]] = []

    for i, word in enumerate(words):
        # Single-token match
        if norm[i] in single_fillers and word.end > word.start:
            cuts.append((word.start, word.end))

        # Phrase matches anchored at this index
        for phrase in phrase_fillers:
            length = len(phrase)
            if i + length > len(words):
                continue
            if norm[i : i + length] != phrase:
                continue
            first = words[i]
            last = words[i + length - 1]
            if last.end > first.start:
                cuts.append((first.start, last.end))

    return cuts


def detect_word_gap_silence(
    transcript: list[TranscriptSegment], min_silence: float
) -> list[tuple[float, float]]:
    """Emit cut ranges for gaps between consecutive words.

    Operates on the flattened, time-sorted word list. A gap
    ``next.start - prev.end >= min_silence`` is emitted as ``(prev.end,
    next.start)``. Leading/trailing silence is not included.
    """
    words = _flatten_words(transcript)
    cuts: list[tuple[float, float]] = []
    for prev, nxt in zip(words, words[1:]):
        if nxt.start - prev.end >= min_silence:
            cuts.append((prev.end, nxt.start))
    return cuts


def detect_dead_air(
    silence_segments: list[tuple[float, float]],
    min_silence: float,
    pad: float = 0.0,
) -> list[tuple[float, float]]:
    """Filter pre-computed silence ranges to cut ranges.

    Keeps silences with duration ``>= min_silence``, then shrinks each by
    ``pad`` seconds on each side: ``(start + pad, end - pad)``. Ranges that
    become non-positive in length after padding are dropped.
    """
    cuts: list[tuple[float, float]] = []
    for start, end in silence_segments:
        if end - start < min_silence:
            continue
        padded_start = start + pad
        padded_end = end - pad
        if padded_end > padded_start:
            cuts.append((padded_start, padded_end))
    return cuts
