"""Render an assembled vlog timeline via a single ffmpeg pass.

This module trims each included storyboard segment from its source clip,
concatenates them in order, optionally burns in ASS/SRT subtitles, and
encodes the result to a single output file.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from vlogkit.models import ClipAnalysis, Storyboard, StoryboardSegment

_RESOLUTION_PRESETS = {
    "2160p": (3840, 2160), "1440p": (2560, 1440), "1080p": (1920, 1080),
    "720p": (1280, 720), "480p": (854, 480),
}


def parse_resolution(spec: str | None) -> tuple[int, int] | None:
    """Parse '1080p'|'720p'|...|'WxH' into (width, height); None passes through.

    Raises ValueError on an unrecognized spec.
    """
    if not spec:
        return None
    s = spec.strip().lower()
    if s in _RESOLUTION_PRESETS:
        return _RESOLUTION_PRESETS[s]
    if "x" in s:
        w, h = s.split("x", 1)
        return (int(w), int(h))
    raise ValueError(f"Unrecognized resolution {spec!r}; use a preset (1080p/720p/...) or WxH")


def pick_render_target(
    storyboard: Storyboard,
    analyses: list[ClipAnalysis] | dict,
    default_res: tuple[int, int] = (1920, 1080),
    default_fps: float = 30.0,
) -> tuple[tuple[int, int], float]:
    """Choose an output resolution + fps for the render.

    Picks the largest-area frame among included clips (so nothing is upscaled
    past its source), using that clip's fps. Falls back to the defaults when no
    analysis is available for any included clip.
    """
    if isinstance(analyses, dict):
        table = analyses
    else:
        table: dict = {}
        for a in analyses:
            table.setdefault(a.metadata.path.resolve(), a)
            table.setdefault(a.metadata.path.name, a)

    best_res = None
    best_fps = default_fps
    best_area = -1
    for seg in included_segments(storyboard):
        a = (
            table.get(seg.clip_path.resolve())
            or table.get(str(seg.clip_path))
            or table.get(seg.clip_path.name)
        )
        if a is None:
            continue
        w, h = a.metadata.resolution
        area = w * h
        if area > best_area:
            best_area = area
            best_res = (w, h)
            best_fps = a.metadata.fps
    if best_res is None:
        return default_res, default_fps
    return best_res, best_fps


def included_segments(storyboard: Storyboard) -> list[StoryboardSegment]:
    """Flatten all sections' segments in order, keeping only include=True."""
    segments: list[StoryboardSegment] = []
    for section in storyboard.sections:
        for seg in section.segments:
            if seg.include:
                segments.append(seg)
    return segments


def _escape_subtitle_path(p: Path) -> str:
    """Escape a path for use in the ffmpeg ``subtitles`` filter.

    Returns the ``filename='...'`` argument value with backslash, colon, and
    single-quote escaped per libass/ffmpeg filtergraph rules.
    """
    raw = str(p)
    # Order matters: escape backslashes first so we do not double-escape the
    # backslashes we introduce for the other characters.
    escaped = raw.replace("\\", "\\\\")
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace("'", "\\'")
    return f"filename='{escaped}'"


def _escape_drawtext(text: str) -> str:
    """Escape text for use inside a ``drawtext`` filter ``text='...'`` value.

    Escapes backslash (first, to avoid double-escaping), colon, single-quote,
    and percent — the characters that have special meaning to the filtergraph
    parser / drawtext expansion.
    """
    escaped = text.replace("\\", "\\\\")
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace("'", "\\'")
    escaped = escaped.replace("%", "\\%")
    return escaped


def build_ffmpeg_command(
    segments: list[StoryboardSegment],
    subtitle_path: Path | None,
    output_path: Path,
    fps: float = 30.0,
    ffmpeg_bin: str = "ffmpeg",
    resolution: tuple[int, int] | None = None,
    audio_cleanup: bool = False,
    denoise: bool = False,
    title_card: str | None = None,
    lower_thirds: bool = False,
) -> list[str]:
    """Build the argv list for a single ffmpeg pass.

    Trims each segment from its source clip, concatenates them in order,
    optionally burns subtitles onto the concatenated video, and writes
    ``output_path``. Pure function — performs no execution.

    When ``resolution`` is given as ``(width, height)``, each segment's video is
    scaled to fit and letterboxed/pillarboxed to those exact dimensions and its
    audio is resampled to a common format, so clips of differing resolution,
    aspect ratio, or audio layout concatenate cleanly. When ``None`` the legacy
    behavior (raw trim + concat) is preserved.
    """
    cmd: list[str] = [ffmpeg_bin]

    # One -i input per segment.
    for seg in segments:
        cmd += ["-i", str(seg.clip_path)]

    n = len(segments)

    # Optional normalization filters, applied per segment before concat.
    if resolution is not None:
        w, h = resolution
        vnorm = (
            f",scale={w}:{h}:force_original_aspect_ratio=decrease"
            f",pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
        )
        anorm = ",aformat=sample_rates=48000:channel_layouts=stereo"
    else:
        vnorm = ""
        anorm = ""

    # Per-input trim chains.
    chains: list[str] = []
    concat_inputs = ""
    for i, seg in enumerate(segments):
        start = seg.in_point
        end = seg.out_point
        # Optional per-segment lower-third overlay: drawtext of the segment's
        # label near the bottom-left, shown for the first ~3s of the segment.
        lt = ""
        if lower_thirds and seg.label:
            label_txt = _escape_drawtext(seg.label)
            lt = (
                f",drawtext=text='{label_txt}'"
                ":fontcolor=white:fontsize=24:box=1:boxcolor=black@0.5:boxborderw=10"
                ":x=40:y=h-th-40:enable='lt(t,3)'"
            )
        chains.append(
            f"[{i}:v]trim=start={start}:end={end},setpts=PTS-STARTPTS{vnorm}{lt}[v{i}];"
            f"[{i}:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS{anorm}[a{i}];"
        )
        concat_inputs += f"[v{i}][a{i}]"

    concat = f"{concat_inputs}concat=n={n}:v=1:a={1}[vc][ac];"

    filtergraph = "".join(chains) + concat

    # Video post-processing on the concatenated stream: subtitles -> title card.
    video_label = "[vc]"
    if subtitle_path is not None:
        sub_arg = _escape_subtitle_path(subtitle_path)
        filtergraph += f"{video_label}subtitles={sub_arg}[vout];"
        video_label = "[vout]"

    if title_card is not None:
        title_txt = _escape_drawtext(title_card)
        filtergraph += (
            f"{video_label}drawtext=text='{title_txt}'"
            ":fontcolor=white:fontsize=72:borderw=4:bordercolor=black"
            ":x=(w-text_w)/2:y=(h-text_h)/2:enable='lt(t,3)'[vtitle];"
        )
        video_label = "[vtitle]"

    # Audio post-processing on the concatenated stream: optional denoise +
    # loudness normalization to a YouTube-friendly target.
    audio_label = "[ac]"
    if audio_cleanup or denoise:
        afilters: list[str] = []
        if denoise:
            afilters.append("afftdn=nf=-25")
        if audio_cleanup:
            afilters.append("loudnorm=I=-14:TP=-1.5:LRA=11")
        filtergraph += f"{audio_label}{','.join(afilters)}[aout];"
        audio_label = "[aout]"

    # Strip the trailing ';' so the graph ends cleanly.
    filtergraph = filtergraph.rstrip(";")

    cmd += ["-filter_complex", filtergraph]
    cmd += ["-map", video_label, "-map", audio_label]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"]
    cmd += ["-r", str(fps)]
    cmd += ["-y", str(output_path)]
    return cmd


def render(
    storyboard: Storyboard,
    output_path: Path,
    subtitle_path: Path | None = None,
    fps: float = 30.0,
    ffmpeg_bin: str = "ffmpeg",
    resolution: tuple[int, int] | None = None,
    audio_cleanup: bool = False,
    denoise: bool = False,
    title_card: str | None = None,
    lower_thirds: bool = False,
) -> Path:
    """Render the storyboard's included segments to ``output_path``.

    Builds the ffmpeg command and runs it. Raises ``RuntimeError`` if there
    are no included segments, if ffmpeg is missing, or if ffmpeg fails. Pass
    ``resolution`` to normalize mixed-size clips (see ``build_ffmpeg_command``).
    """
    segments = included_segments(storyboard)
    if not segments:
        raise RuntimeError("No included segments to render.")

    resolved_bin = shutil.which(ffmpeg_bin)
    if resolved_bin is None:
        raise RuntimeError(
            f"ffmpeg binary {ffmpeg_bin!r} not found on PATH. "
            "Install ffmpeg or pass a valid ffmpeg_bin."
        )

    cmd = build_ffmpeg_command(
        segments, subtitle_path, output_path, fps=fps, ffmpeg_bin=resolved_bin,
        resolution=resolution, audio_cleanup=audio_cleanup, denoise=denoise,
        title_card=title_card, lower_thirds=lower_thirds,
    )

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        tail = "\n".join(stderr.strip().splitlines()[-20:])
        raise RuntimeError(f"ffmpeg failed (exit {exc.returncode}):\n{tail}") from exc

    return output_path
