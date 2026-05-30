"""Generate YouTube chapter markers + a description block from a Storyboard.

Chapters map storyboard sections onto the final edited timeline. YouTube's
rules are honored: the first chapter is always 0:00, chapters are >=10s apart,
and (ideally) there are at least three.
"""

from __future__ import annotations

from ..models import Storyboard


def format_timestamp(seconds: float) -> str:
    """Format seconds as YouTube-style 'M:SS' (or 'H:MM:SS' past an hour)."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _section_duration(section) -> float:
    return sum(
        seg.out_point - seg.in_point for seg in section.segments if seg.include
    )


def build_chapters(storyboard: Storyboard, min_gap: float = 10.0) -> list[tuple[float, str]]:
    """Return ``(start_seconds, title)`` chapters on the final timeline.

    Empty sections (no included segments) are skipped. The first emitted
    chapter is forced to 0:00. Chapters closer than ``min_gap`` to the previous
    kept chapter are dropped (YouTube requires >=10s spacing).
    """
    raw: list[tuple[float, str]] = []
    offset = 0.0
    for section in storyboard.sections:
        dur = _section_duration(section)
        if dur <= 0:
            continue  # skip empty sections
        raw.append((offset, section.title))
        offset += dur

    if not raw:
        return []

    # Force the first chapter to 0:00.
    raw[0] = (0.0, raw[0][1])

    chapters: list[tuple[float, str]] = [raw[0]]
    for start, title in raw[1:]:
        if start - chapters[-1][0] >= min_gap:
            chapters.append((start, title))
        # else: too close to the previous chapter — fold it away.
    return chapters


def chapters_to_text(chapters: list[tuple[float, str]]) -> str:
    """Render chapters as newline-separated 'M:SS Title' lines."""
    return "\n".join(f"{format_timestamp(start)} {title}" for start, title in chapters)


def build_description(
    storyboard: Storyboard,
    chapters: list[tuple[float, str]],
    intro: str = "",
) -> str:
    """Build a YouTube description: title, optional blurb, then the chapters."""
    parts: list[str] = [storyboard.title]
    blurb = intro.strip() or storyboard.llm_rationale.strip()
    if blurb:
        parts.append(blurb)
    if chapters:
        parts.append("Chapters:\n" + chapters_to_text(chapters))
    return "\n\n".join(parts)
