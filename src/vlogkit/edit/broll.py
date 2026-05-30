"""B-roll / cutaway *suggestion* engine.

This is an analysis-only feature: it never touches ffmpeg or renders anything.
It inspects an assembled :class:`~vlogkit.models.Storyboard` plus the per-clip
:class:`~vlogkit.models.ClipAnalysis` records and returns structured
:class:`BrollSuggestion` objects telling a human (or the UI) *where* on the
final timeline a cutaway would help and *which* scene to cut away to.

Concept
-------
A B-roll *opportunity* is a stretch of the edit dominated by talking
(narration) — the viewer is just watching a head talk for a while. Cutting
away to a visually interesting shot keeps the edit alive. Candidate B-roll
scenes are the highest-*aesthetic* scenes across all clips (pretty visuals).

Three pure, side-effect-free functions:

* :func:`find_talking_stretches` — narration-heavy spans, remapped to the
  final concatenated timeline (same offset accounting as the caption cue
  builder: ``offset`` advances by each *included* segment's duration).
* :func:`rank_broll_scenes` — candidate scenes ordered by aesthetic score.
* :func:`suggest_broll` — pairs the longest talking stretches with the best
  unused aesthetic scenes and emits :class:`BrollSuggestion` objects.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from vlogkit.models import ClipAnalysis, Storyboard

# Shortest scene we will cut away to. Anything briefer feels like a flicker.
_MIN_SOURCE_SCENE = 2.0
# Longest single cutaway we will suggest.
_MAX_CUTAWAY = 5.0


class BrollSuggestion(BaseModel):
    """A single suggested cutaway, timed against the FINAL rendered timeline."""

    timeline_start: float
    timeline_end: float
    trigger_text: str
    source_clip: str
    source_start: float
    source_end: float
    score: float
    reason: str = ""


# --------------------------------------------------------------------------- #
# Clip lookup (mirrors vlogkit.captions.cues)
# --------------------------------------------------------------------------- #
def _build_lookup(analyses: list[ClipAnalysis] | dict) -> dict[str, ClipAnalysis]:
    if isinstance(analyses, dict):
        return analyses
    lookup: dict[str, ClipAnalysis] = {}
    for a in analyses:
        lookup.setdefault(str(a.metadata.path.resolve()), a)
        lookup.setdefault(a.metadata.path.name, a)
    return lookup


def _resolve_analysis(clip_path: Path, lookup: dict[str, ClipAnalysis]) -> ClipAnalysis | None:
    for key in (str(clip_path.resolve()), str(clip_path), clip_path.name):
        if key in lookup:
            return lookup[key]
    return None


def _aesthetic(scene) -> float:
    return scene.murch.aesthetic if scene.murch is not None else 0.0


# --------------------------------------------------------------------------- #
# 1. find_talking_stretches
# --------------------------------------------------------------------------- #
def find_talking_stretches(
    storyboard: Storyboard,
    analyses: list[ClipAnalysis] | dict,
    min_len: float = 4.0,
) -> list[tuple[float, float, str]]:
    """Find narration-heavy spans on the final timeline.

    Walks the *included* segments, accumulating ``offset`` by each segment's
    on-screen duration (out - in). For each segment we collect the transcript
    text overlapping the segment window ``[in_point, out_point]``. If the
    window is at least ``min_len`` long and contains any transcript text, the
    whole window is treated as one talking stretch, remapped onto the final
    timeline.

    Returns ``(timeline_start, timeline_end, joined_text)`` per stretch.
    """
    lookup = _build_lookup(analyses)
    stretches: list[tuple[float, float, str]] = []
    offset = 0.0

    for section in storyboard.sections:
        for seg in section.segments:
            if not seg.include:
                continue

            in_point = seg.in_point
            out_point = seg.out_point
            window = out_point - in_point

            analysis = _resolve_analysis(seg.clip_path, lookup)
            if analysis is not None and window >= min_len:
                texts = [
                    ts.text.strip()
                    for ts in analysis.transcript
                    if ts.end > in_point and ts.start < out_point and ts.text.strip()
                ]
                if texts:
                    stretches.append((offset, offset + window, " ".join(texts)))

            # Advance even when the segment yielded no stretch so later
            # segments stay aligned to the final timeline.
            offset += window

    return stretches


# --------------------------------------------------------------------------- #
# 2. rank_broll_scenes
# --------------------------------------------------------------------------- #
def rank_broll_scenes(
    analyses: list[ClipAnalysis],
    exclude_clip: Path | None = None,
    top_n: int = 10,
) -> list[tuple[Path, float, float, float]]:
    """All scenes across clips as ``(clip_path, start, end, aesthetic)``,
    sorted by aesthetic descending (missing Murch score -> 0). Scenes from
    ``exclude_clip`` are dropped. Returns at most ``top_n`` scenes.
    """
    exclude = exclude_clip.resolve() if exclude_clip is not None else None

    scored: list[tuple[Path, float, float, float]] = []
    for a in analyses:
        clip_path = a.metadata.path
        if exclude is not None and clip_path.resolve() == exclude:
            continue
        for scene in a.scenes:
            scored.append((clip_path, scene.start, scene.end, _aesthetic(scene)))

    scored.sort(key=lambda row: row[3], reverse=True)
    return scored[:top_n]


# --------------------------------------------------------------------------- #
# 3. suggest_broll
# --------------------------------------------------------------------------- #
def suggest_broll(
    storyboard: Storyboard,
    analyses: list[ClipAnalysis],
    max_suggestions: int = 5,
    min_stretch: float = 4.0,
) -> list[BrollSuggestion]:
    """Pair the longest talking stretches with the best unused aesthetic
    scenes, emitting :class:`BrollSuggestion` objects.

    Heuristic
    ---------
    * Talking stretches are served longest-first (they benefit most).
    * Candidate scenes are ranked by aesthetic; we walk them in order and never
      reuse a scene. Scenes shorter than ``_MIN_SOURCE_SCENE`` are skipped.
    * Each cutaway starts a little into its stretch (so the narration is
      established first) and runs for ``min(stretch_len, scene_len, _MAX_CUTAWAY)``
      seconds, always staying within the stretch bounds.
    * Capped at ``max_suggestions``. Returns ``[]`` when there are no talking
      stretches or no scored scenes.
    """
    stretches = find_talking_stretches(storyboard, analyses, min_len=min_stretch)
    if not stretches:
        return []

    scenes = rank_broll_scenes(analyses, top_n=len(analyses) * 50 or 50)
    # Only scenes long enough to be a real cutaway.
    candidates = [s for s in scenes if (s[2] - s[1]) >= _MIN_SOURCE_SCENE]
    if not candidates:
        return []

    # Longest stretches first.
    stretches.sort(key=lambda s: (s[1] - s[0]), reverse=True)

    suggestions: list[BrollSuggestion] = []
    scene_idx = 0

    for t_start, t_end, text in stretches:
        if len(suggestions) >= max_suggestions:
            break
        if scene_idx >= len(candidates):
            break

        clip_path, src_start, src_end, score = candidates[scene_idx]
        scene_idx += 1  # never reuse this scene

        stretch_len = t_end - t_start
        scene_len = src_end - src_start
        cutaway = min(stretch_len, scene_len, _MAX_CUTAWAY)

        # Start a bit into the stretch (let narration establish) but keep the
        # cutaway fully inside the stretch bounds.
        lead_in = min(1.0, max(0.0, stretch_len - cutaway))
        cut_start = t_start + lead_in
        cut_end = cut_start + cutaway
        if cut_end > t_end:
            cut_end = t_end
            cut_start = cut_end - cutaway

        suggestions.append(
            BrollSuggestion(
                timeline_start=cut_start,
                timeline_end=cut_end,
                trigger_text=text,
                source_clip=str(clip_path),
                source_start=src_start,
                source_end=src_start + cutaway,
                score=score,
                reason="Cut away to high-aesthetic shot during narration",
            )
        )

    return suggestions
