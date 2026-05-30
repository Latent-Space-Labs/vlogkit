"""Thumbnail generation: pick the most visually striking frames and render JPGs.

Ranks scenes across analyzed clips by their Murch *aesthetic* score, then renders
JPG thumbnails via ffmpeg, optionally burning in a bold title overlay.

Title overlay uses ffmpeg's `drawtext` filter, which requires an ffmpeg built with
freetype. Homebrew's plain `ffmpeg` formula does NOT ship freetype/drawtext; the
keg-only `ffmpeg-full` formula does. `has_drawtext` probes for the filter and
`make_thumbnails` silently drops the title when it is unavailable rather than
failing the render.
"""

from __future__ import annotations

import functools
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from ..ffmpeg_util import _which, resolve_ffmpeg

if TYPE_CHECKING:  # pragma: no cover
    from ..models import ClipAnalysis
    from ..project import Project


@functools.lru_cache(maxsize=16)
def has_drawtext(ffmpeg_bin: str) -> bool:
    """True if the given ffmpeg exposes the `drawtext` filter (needs freetype)."""
    exe = _which(ffmpeg_bin)
    if exe is None:
        return False
    try:
        out = subprocess.run(
            [exe, "-hide_banner", "-filters"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return False
    return " drawtext " in out.stdout


def rank_thumbnail_candidates(
    analyses: list[ClipAnalysis], top_n: int = 3
) -> list[tuple[Path, float, float]]:
    """Rank every scene across clips by aesthetic score.

    Returns up to ``top_n`` ``(clip_path, timestamp, aesthetic_score)`` tuples,
    sorted by score descending. ``timestamp`` is the scene midpoint; a missing
    Murch score counts as ``0.0``.
    """
    candidates: list[tuple[Path, float, float]] = []
    for analysis in analyses:
        clip_path = analysis.metadata.path
        for scene in analysis.scenes:
            timestamp = (scene.start + scene.end) / 2
            score = scene.murch.aesthetic if scene.murch is not None else 0.0
            candidates.append((clip_path, timestamp, score))
    candidates.sort(key=lambda c: c[2], reverse=True)
    return candidates[:top_n]


def _escape_drawtext(text: str) -> str:
    """Escape a string for use inside a drawtext ``text='...'`` value."""
    # Order matters: backslash first so we don't double-escape inserted slashes.
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace("%", "\\%")
    return text


def build_thumbnail_command(
    clip_path: Path,
    timestamp: float,
    output_path: Path,
    title: str | None = None,
    resolution: tuple[int, int] = (1280, 720),
    ffmpeg_bin: str = "ffmpeg",
    font_size: int = 72,
) -> list[str]:
    """Build the ffmpeg argv to extract one frame as a JPG thumbnail.

    Seeks to ``timestamp``, grabs a single frame, scales+crops to fill
    ``resolution``, and (if ``title`` is given) burns a bold centered title near
    the bottom via drawtext.
    """
    width, height = resolution
    filters = [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
    ]
    if title:
        escaped = _escape_drawtext(title)
        filters.append(
            f"drawtext=text='{escaped}'"
            f":fontcolor=white:fontsize={font_size}"
            f":borderw=4:bordercolor=black"
            f":x=(w-text_w)/2:y=h-text_h-60"
        )
    vf = ",".join(filters)
    return [
        ffmpeg_bin,
        "-ss", str(timestamp),
        "-i", str(clip_path),
        "-frames:v", "1",
        "-vf", vf,
        "-y", str(output_path),
    ]


def make_thumbnails(
    project: Project,
    output_dir: Path | None = None,
    *,
    title: str | None = None,
    count: int = 3,
    resolution: tuple[int, int] = (1280, 720),
    ffmpeg_bin: str | None = None,
) -> list[Path]:
    """Render up to ``count`` thumbnail JPGs from the project's top-aesthetic scenes.

    Raises ``RuntimeError`` if there are no scored candidates or if a render fails.
    When ``title`` is given but the resolved ffmpeg lacks drawtext, the title is
    dropped and thumbnails render without it.
    """
    ffmpeg_bin = ffmpeg_bin or resolve_ffmpeg(project.settings.ffmpeg_path or None)

    candidates = rank_thumbnail_candidates(project.load_all_analyses(), top_n=count)
    if not candidates:
        raise RuntimeError("No thumbnail candidates: no analyzed scenes found.")

    effective_title = title
    if title and not has_drawtext(ffmpeg_bin):
        # No freetype/drawtext available — render without the title rather than crash.
        effective_title = None

    output_dir = output_dir or (project.cache_dir / "thumbnails")
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for i, (clip_path, timestamp, _score) in enumerate(candidates, start=1):
        out_path = output_dir / f"thumb_{i}.jpg"
        cmd = build_thumbnail_command(
            clip_path,
            timestamp,
            out_path,
            title=effective_title,
            resolution=resolution,
            ffmpeg_bin=ffmpeg_bin,
        )
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode("utf-8", "replace")
            tail = stderr[-1000:]
            raise RuntimeError(
                f"ffmpeg failed to render {out_path.name}: {tail}"
            ) from exc
        written.append(out_path)

    return written
