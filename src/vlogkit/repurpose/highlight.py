"""Auto-assemble a highlight reel / supercut from the best-scored scenes.

Flattens every scene across all analyzed clips, ranks them by their Murch
composite score, greedily packs the highest-scored scenes into a target
duration budget, then renders the selection to a single MP4 via the shared
caption/render ffmpeg pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from vlogkit.captions.render import pick_render_target, render
from vlogkit.ffmpeg_util import resolve_ffmpeg
from vlogkit.models import (
    ClipAnalysis,
    Storyboard,
    StoryboardSection,
    StoryboardSegment,
)

if TYPE_CHECKING:
    from vlogkit.project import Project

# (clip_path, start, end, score)
Scene = tuple[Path, float, float, float]


def select_highlight_scenes(
    analyses: list[ClipAnalysis],
    max_duration: float = 60.0,
    order: str = "chronological",
) -> list[Scene]:
    """Select the best scenes across all clips, capped to ``max_duration``.

    Flattens every scene into ``(clip_path, start, end, score)`` where ``score``
    is the Murch composite (``0.0`` when unscored). Greedily picks the
    highest-scored scenes first; a scene whose duration exceeds the remaining
    budget is skipped (and we keep trying smaller, lower-scored ones). The
    selected scenes are then sorted:

    - ``order == "chronological"`` -> by ``(clip_path, start)``
    - ``order == "score"`` -> by descending score

    Pure function — no I/O. Returns ``[]`` when there are no scenes.
    """
    # Flatten all scenes across clips.
    flat: list[Scene] = []
    for analysis in analyses:
        clip_path = analysis.metadata.path
        for scene in analysis.scenes:
            score = scene.murch.composite if scene.murch is not None else 0.0
            flat.append((clip_path, scene.start, scene.end, score))

    if not flat:
        return []

    # Greedy: try highest-score scenes first. Ties broken by chronological
    # position so the fallback (all unscored) is a stable time order.
    ranked = sorted(flat, key=lambda s: (-s[3], s[0].as_posix(), s[1]))

    selected: list[Scene] = []
    remaining = max_duration
    for scene in ranked:
        duration = scene[2] - scene[1]
        if duration <= remaining:
            selected.append(scene)
            remaining -= duration
        # else: too long for what's left; keep scanning for smaller scenes.

    if order == "score":
        selected.sort(key=lambda s: -s[3])
    else:  # chronological
        selected.sort(key=lambda s: (s[0].as_posix(), s[1]))

    return selected


def build_highlight_storyboard(scenes: list[Scene], title: str = "Highlights") -> Storyboard:
    """Build a single-section storyboard, one included segment per scene. Pure."""
    segments = [
        StoryboardSegment(
            clip_path=clip_path,
            in_point=start,
            out_point=end,
            include=True,
        )
        for (clip_path, start, end, _score) in scenes
    ]
    section = StoryboardSection(title=title, segments=segments)
    return Storyboard(title=title, sections=[section])


def make_highlight(
    project: Project,
    output_path: Path | None = None,
    *,
    max_duration: float = 60.0,
    order: str = "chronological",
    ffmpeg_bin: str | None = None,
) -> Path:
    """Assemble and render a highlight reel for ``project``.

    Loads all cached analyses, selects the best scenes (capped to
    ``max_duration``), builds a storyboard, picks a render target, and renders
    to an MP4. Raises ``RuntimeError`` if no scenes are available.
    Output defaults to ``project.cache_dir / "highlight.mp4"``.
    """
    analyses = project.load_all_analyses()
    scenes = select_highlight_scenes(analyses, max_duration=max_duration, order=order)
    if not scenes:
        raise RuntimeError(
            "No scenes available to build a highlight reel. "
            "Run `vlogkit analyze` (with scene scoring) first."
        )

    storyboard = build_highlight_storyboard(scenes)
    resolution, fps = pick_render_target(storyboard, analyses)

    if ffmpeg_bin is None:
        ffmpeg_bin = resolve_ffmpeg(project.settings.ffmpeg_path or None)

    if output_path is None:
        output_path = project.cache_dir / "highlight.mp4"

    return render(
        storyboard,
        output_path,
        fps=fps,
        ffmpeg_bin=ffmpeg_bin,
        resolution=resolution,
    )
