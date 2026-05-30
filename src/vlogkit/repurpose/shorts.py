"""Vertical "Shorts" extraction: pick the most engaging window, reframe to 9:16.

Given an analyzed + Murch-scored project, ``make_short`` auto-selects the single
most engaging 15-60s window from one clip, center-crops it to vertical 9:16 (no
letterbox bars), optionally burns karaoke captions, and writes a ready-to-post
MP4.

Three pieces, separable for testing:

* ``pick_short_window`` — pure window selection over clip scenes.
* ``build_vertical_command`` — pure ffmpeg argv builder (trim + center-crop fill).
* ``make_short`` — orchestrates selection, caption generation, and the ffmpeg run.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from vlogkit.captions.pipeline import generate_caption_file
from vlogkit.ffmpeg_util import has_libass, resolve_ffmpeg
from vlogkit.models import (
    CaptionStyle,
    ClipAnalysis,
    SceneSegment,
    Storyboard,
    StoryboardSection,
    StoryboardSegment,
)

if TYPE_CHECKING:
    from vlogkit.project import Project


def _scene_score(scene: SceneSegment) -> float:
    """Engagement score for a scene: prefer Murch impact, fall back to composite.

    A missing/``None`` Murch score counts as 0.
    """
    m = scene.murch
    if m is None:
        return 0.0
    if m.impact:
        return float(m.impact)
    return float(m.composite or 0.0)


def pick_short_window(
    analyses: list[ClipAnalysis],
    min_dur: float = 15.0,
    max_dur: float = 60.0,
) -> tuple[Path, float, float] | None:
    """Pick the single most engaging vertical-Short window from one clip.

    Scans each clip's scenes for the contiguous run (within ONE clip) whose total
    duration falls in ``[min_dur, max_dur]`` and whose mean Murch score is highest
    (preferring ``.impact``, falling back to ``.composite``, treating ``None`` as
    0). Returns ``(clip_path, start, end)`` for the best window.

    Edge cases:

    * A single scene longer than ``max_dur`` is clamped to ``max_dur`` from its
      start.
    * If no clip can produce an in-range run, fall back to the full span of the
      single best clip (better a short Short than nothing) — its scenes' summed
      duration, clamped to ``max_dur``.
    * ``None`` if there is no usable footage at all.
    """
    best_window: tuple[Path, float, float] | None = None
    best_score = float("-inf")

    # Fallback bookkeeping: best whole-clip span when nothing fits the range.
    fb_window: tuple[Path, float, float] | None = None
    fb_score = float("-inf")

    for analysis in analyses:
        scenes = analysis.scenes
        if not scenes:
            continue
        clip_path = analysis.metadata.path

        # --- in-range contiguous runs ------------------------------------- #
        n = len(scenes)
        for i in range(n):
            run_dur = 0.0
            run_total = 0.0
            for j in range(i, n):
                run_dur += scenes[j].end - scenes[j].start
                run_total += _scene_score(scenes[j])

                if run_dur > max_dur:
                    # A single scene already overflows -> clamp it and stop.
                    if i == j:
                        score = _scene_score(scenes[i])
                        if score > best_score:
                            best_score = score
                            best_window = (
                                clip_path,
                                scenes[i].start,
                                scenes[i].start + max_dur,
                            )
                    break

                if run_dur >= min_dur:
                    if run_total > best_score:
                        best_score = run_total
                        best_window = (clip_path, scenes[i].start, scenes[j].end)

        # --- fallback: whole-clip span ------------------------------------ #
        span_start = scenes[0].start
        span_end = scenes[-1].end
        if span_end - span_start > max_dur:
            span_end = span_start + max_dur
        total = sum(_scene_score(s) for s in scenes)
        if total > fb_score:
            fb_score = total
            fb_window = (clip_path, span_start, span_end)

    if best_window is not None:
        return best_window
    return fb_window


def _escape_subtitle_path(p: Path) -> str:
    """Escape a path for the ffmpeg ``subtitles`` filter (``filename='...'``).

    Escapes backslash, colon, and single-quote per libass/ffmpeg filtergraph
    rules. Backslashes are escaped first to avoid double-escaping.
    """
    raw = str(p)
    escaped = raw.replace("\\", "\\\\")
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace("'", "\\'")
    return f"filename='{escaped}'"


def build_vertical_command(
    clip_path: Path,
    start: float,
    end: float,
    output_path: Path,
    subtitle_path: Path | None,
    resolution: tuple[int, int] = (1080, 1920),
    fps: float = 30.0,
    ffmpeg_bin: str = "ffmpeg",
) -> list[str]:
    """Build the ffmpeg argv to trim + reframe a window to vertical 9:16.

    Single input. Filter chain: trim ``[start, end]`` (reset PTS), then fill the
    target 9:16 frame by CENTER-CROP (no letterbox bars) via
    ``scale=W:H:force_original_aspect_ratio=increase,crop=W:H,setsar=1,fps=...``.
    When ``subtitle_path`` is given, a ``subtitles`` filter is appended to burn
    the captions in. Pure function — performs no execution.
    """
    w, h = resolution

    vchain = (
        f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,"
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},setsar=1,fps={fps}"
    )
    if subtitle_path is not None:
        vchain += f",subtitles={_escape_subtitle_path(subtitle_path)}"
    vchain += "[vout];"

    achain = f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[aout]"

    filtergraph = vchain + achain

    cmd: list[str] = [ffmpeg_bin, "-i", str(clip_path)]
    cmd += ["-filter_complex", filtergraph]
    cmd += ["-map", "[vout]", "-map", "[aout]"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"]
    cmd += ["-r", str(fps)]
    cmd += ["-y", str(output_path)]
    return cmd


def make_short(
    project: Project,
    output_path: Path | None = None,
    *,
    min_dur: float = 15.0,
    max_dur: float = 60.0,
    captions: bool = True,
    ffmpeg_bin: str | None = None,
) -> Path:
    """Auto-pick, reframe, caption, and render the most engaging vertical Short.

    Selects the best window across the project's analyses (``pick_short_window``),
    builds a one-segment storyboard for it, optionally burns karaoke ASS captions
    (when ``captions`` and the resolved ffmpeg has libass), and renders a vertical
    9:16 MP4 to ``output_path`` (default ``project.cache_dir/"short.mp4"``).

    Raises ``RuntimeError`` if no usable window exists or if ffmpeg fails.
    """
    bin_path = ffmpeg_bin or resolve_ffmpeg(project.settings.ffmpeg_path or None)

    analyses = project.load_all_analyses()
    window = pick_short_window(analyses, min_dur=min_dur, max_dur=max_dur)
    if window is None:
        raise RuntimeError(
            "No usable footage for a Short: analyze + score the project first."
        )
    clip_path, start, end = window

    if output_path is None:
        output_path = project.cache_dir / "short.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # The Short's timeline starts at 0 but the window starts mid-clip; encode the
    # window as in_point/out_point so caption cues map onto the trimmed output.
    segment = StoryboardSegment(
        clip_path=clip_path,
        in_point=start,
        out_point=end,
        label="short",
        include=True,
    )
    storyboard = Storyboard(
        title="Short",
        sections=[StoryboardSection(title="Short", segments=[segment])],
    )

    subtitle_path: Path | None = None
    if captions and has_libass(bin_path):
        subtitle_path = generate_caption_file(
            storyboard,
            analyses,
            fmt="ass",
            output_path=project.cache_dir / "short.ass",
            style=CaptionStyle(karaoke=True),
        )

    cmd = build_vertical_command(
        clip_path,
        start,
        end,
        output_path,
        subtitle_path,
        ffmpeg_bin=bin_path,
    )

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        tail = "\n".join(stderr.strip().splitlines()[-20:])
        raise RuntimeError(f"ffmpeg failed (exit {exc.returncode}):\n{tail}") from exc

    return output_path
