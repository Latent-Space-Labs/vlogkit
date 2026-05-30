"""Tighten a storyboard by auto-cutting silence + filler words.

Reuses the detectors (detect.py) and pure interval algebra (intervals.py) to
rewrite each included segment into one or more tighter sub-segments, dropping
dead air and fillers. The result is an ordinary Storyboard, so it flows through
export / captions / render unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel
from rich.console import Console

from ..models import (
    ClipAnalysis,
    Storyboard,
    StoryboardSection,
    StoryboardSegment,
    TightenConfig,
)
from .detect import detect_dead_air, detect_filler_words, detect_word_gap_silence
from .intervals import (
    filter_min_length,
    invert_intervals,
    merge_intervals,
    total_duration,
)


console = Console()


def load_tighten_config(project_root: Path) -> TightenConfig:
    """Load `.vlogkit/tighten.json` overrides, merged over defaults.

    Mirrors the caption-style / score-weights override convention.
    """
    override_path = project_root / ".vlogkit" / "tighten.json"
    if not override_path.exists():
        return TightenConfig()
    try:
        data = json.loads(override_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[yellow]tighten.json could not be loaded ({e}); using defaults.[/]")
        return TightenConfig()
    if not isinstance(data, dict):
        return TightenConfig()
    return TightenConfig.model_validate({**TightenConfig().model_dump(), **data})


class TightenStats(BaseModel):
    original_duration: float = 0.0
    tightened_duration: float = 0.0
    segments_before: int = 0
    segments_after: int = 0

    @property
    def removed_duration(self) -> float:
        return max(0.0, self.original_duration - self.tightened_duration)


def collect_cuts(
    analysis: ClipAnalysis,
    window: tuple[float, float],
    config: TightenConfig,
) -> list[tuple[float, float]]:
    """Gather all cut ranges (filler + silence) for a clip, merged & sorted.

    Cuts are in clip-local time; callers clamp them to the segment window.
    """
    cuts: list[tuple[float, float]] = []
    if config.remove_fillers:
        cuts += detect_filler_words(analysis.transcript, config.fillers)
    if config.remove_silence:
        cuts += detect_word_gap_silence(analysis.transcript, config.min_silence)
        if analysis.audio is not None:
            cuts += detect_dead_air(
                analysis.audio.silence_segments, config.min_silence, config.pad
            )
    return merge_intervals(cuts)


def _lookup(analyses: list[ClipAnalysis] | dict) -> dict:
    if isinstance(analyses, dict):
        return analyses
    table: dict = {}
    for a in analyses:
        table.setdefault(a.metadata.path.resolve(), a)
        table.setdefault(a.metadata.path.name, a)
    return table


def _resolve(table: dict, clip_path: Path) -> ClipAnalysis | None:
    return (
        table.get(clip_path.resolve())
        or table.get(str(clip_path))
        or table.get(clip_path.name)
    )


def tighten_storyboard(
    storyboard: Storyboard,
    analyses: list[ClipAnalysis] | dict,
    config: TightenConfig | None = None,
) -> tuple[Storyboard, TightenStats]:
    """Return a tightened copy of the storyboard plus before/after stats.

    Excluded segments and segments without an analysis pass through unchanged.
    If tightening would erase a whole segment, the original is kept (safety).
    """
    config = config or TightenConfig()
    table = _lookup(analyses)

    original_dur = 0.0
    tightened_dur = 0.0
    segs_before = 0
    segs_after = 0

    new_sections: list[StoryboardSection] = []
    for section in storyboard.sections:
        new_segments: list[StoryboardSegment] = []
        for seg in section.segments:
            segs_before += 1
            seg_len = max(0.0, seg.out_point - seg.in_point)

            if not seg.include:
                new_segments.append(seg.model_copy())
                segs_after += 1
                continue

            original_dur += seg_len
            analysis = _resolve(table, seg.clip_path)
            if analysis is None:
                new_segments.append(seg.model_copy())
                tightened_dur += seg_len
                segs_after += 1
                continue

            window = (seg.in_point, seg.out_point)
            cuts = collect_cuts(analysis, window, config)
            keeps = invert_intervals(window, cuts)
            keeps = filter_min_length(keeps, config.min_keep)

            if not keeps:
                # Tightening erased everything — keep original rather than lose content.
                new_segments.append(seg.model_copy())
                tightened_dur += seg_len
                segs_after += 1
                continue

            for k_start, k_end in keeps:
                new_segments.append(
                    seg.model_copy(update={"in_point": k_start, "out_point": k_end})
                )
                segs_after += 1
            tightened_dur += total_duration(keeps)

        new_sections.append(
            StoryboardSection(title=section.title, segments=new_segments, notes=section.notes)
        )

    tightened = Storyboard(
        title=storyboard.title,
        sections=new_sections,
        total_duration=tightened_dur,
        llm_rationale=storyboard.llm_rationale,
    )
    stats = TightenStats(
        original_duration=original_dur,
        tightened_duration=tightened_dur,
        segments_before=segs_before,
        segments_after=segs_after,
    )
    return tightened, stats
