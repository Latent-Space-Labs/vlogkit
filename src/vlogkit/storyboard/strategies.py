"""Fallback storyboard strategies (no LLM required)."""

from __future__ import annotations

from ..models import ClipAnalysis, Storyboard, StoryboardSection, StoryboardSegment


def chronological_fallback(analyses: list[ClipAnalysis]) -> Storyboard:
    """Simple chronological ordering — used when no API key is available."""
    sorted_clips = sorted(
        analyses,
        key=lambda a: a.metadata.creation_time or a.metadata.path.name,
    )

    segments = [
        StoryboardSegment(
            clip_path=a.metadata.path,
            in_point=0.0,
            out_point=a.metadata.duration,
            label=a.summary[:80] if a.summary else a.metadata.filename,
            transition="cut",
            include=True,
        )
        for a in sorted_clips
    ]

    total = sum(a.metadata.duration for a in sorted_clips)

    return Storyboard(
        title="Untitled Vlog",
        sections=[StoryboardSection(
            title="All Clips (Chronological)",
            segments=segments,
            notes="Auto-generated chronological order. No LLM was used.",
        )],
        total_duration=total,
        llm_rationale="Fallback: clips ordered by creation time.",
    )
