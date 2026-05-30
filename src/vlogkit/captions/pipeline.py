"""Captions pipeline: style overrides, sidecar file generation, burn-in orchestration.

Ties together cue building (cues.py), serialization (formats.py), and ffmpeg
rendering (render.py). Sidecar files (.srt/.vtt/.ass) need no external tools;
burn-in requires an ffmpeg built with libass.
"""

from __future__ import annotations

import functools
import json
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from ..models import CaptionStyle, ClipAnalysis, Storyboard
from .cues import build_cues
from .formats import cues_to_ass, cues_to_srt, cues_to_vtt

console = Console()

# fmt name -> (file extension, serializer)
EXTENSIONS: dict[str, str] = {"srt": ".srt", "vtt": ".vtt", "ass": ".ass"}

_SERIALIZERS = {
    "srt": lambda cues, style: cues_to_srt(cues),
    "vtt": lambda cues, style: cues_to_vtt(cues),
    "ass": lambda cues, style: cues_to_ass(cues, style),
}


def load_caption_style(project_root: Path) -> CaptionStyle:
    """Load `.vlogkit/caption_style.json` overrides, merged over defaults.

    Partial overrides are honored: unspecified fields keep their defaults.
    Malformed JSON warns and returns defaults unchanged. Mirrors the
    score-weights override convention.
    """
    override_path = project_root / ".vlogkit" / "caption_style.json"
    if not override_path.exists():
        return CaptionStyle()
    try:
        data = json.loads(override_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[yellow]caption_style.json could not be loaded ({e}); using defaults.[/]")
        return CaptionStyle()
    if not isinstance(data, dict):
        return CaptionStyle()
    return CaptionStyle.model_validate({**CaptionStyle().model_dump(), **data})


def generate_caption_file(
    storyboard: Storyboard,
    analyses: list[ClipAnalysis] | dict,
    *,
    fmt: str = "srt",
    output_path: Path,
    style: CaptionStyle | None = None,
) -> Path:
    """Build cues from the storyboard's transcripts and write a sidecar file.

    Timings are on the final (concatenated) timeline, so the file lines up with
    a render of the included segments. Returns the written path.
    """
    if fmt not in _SERIALIZERS:
        raise ValueError(f"Unknown caption format '{fmt}'. Choose from: {', '.join(EXTENSIONS)}")
    style = style or CaptionStyle()
    cues = build_cues(storyboard, analyses, style)
    text = _SERIALIZERS[fmt](cues, style)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text)
    return output_path


@functools.lru_cache(maxsize=8)
def ffmpeg_has_libass(ffmpeg_bin: str = "ffmpeg") -> bool:
    """True if the given ffmpeg exposes the libass `subtitles` filter (burn-in)."""
    exe = shutil.which(ffmpeg_bin)
    if exe is None:
        return False
    try:
        out = subprocess.run(
            [exe, "-hide_banner", "-filters"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return False
    return " subtitles " in out.stdout or "\nsubtitles" in out.stdout or " subtitles\n" in out.stdout
