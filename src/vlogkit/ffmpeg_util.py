"""Locate an ffmpeg binary, preferring one built with libass (for subtitle burn-in).

Homebrew's regular `ffmpeg` formula no longer ships libass; the `ffmpeg-full`
formula does but installs keg-only (off PATH). This resolver checks PATH plus
known keg-only locations and prefers whichever can actually render subtitles.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from collections.abc import Callable, Iterable

# Known keg-only / alternate install locations that tend to include libass.
CANDIDATE_PATHS = [
    "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",  # Apple Silicon Homebrew
    "/usr/local/opt/ffmpeg-full/bin/ffmpeg",     # Intel Homebrew
]


def _which(name: str) -> str | None:
    """Resolve a binary to an executable path (PATH lookup or direct path)."""
    found = shutil.which(name)
    if found:
        return found
    if os.path.isfile(name) and os.access(name, os.X_OK):
        return name
    return None


@functools.lru_cache(maxsize=16)
def has_libass(ffmpeg_bin: str) -> bool:
    """True if the given ffmpeg exposes the libass `subtitles`/`ass` filter."""
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
    text = out.stdout
    return " subtitles " in text or " ass " in text


def resolve_ffmpeg(
    preferred: str | None = None,
    candidates: Iterable[str] | None = None,
    has_libass_fn: Callable[[str], bool] = has_libass,
) -> str:
    """Return the best ffmpeg binary: a libass-capable one if available.

    Search order: `preferred`, plain `ffmpeg` on PATH, then `candidates`
    (defaults to known keg-only locations). The first existing binary that
    reports libass support wins. If none have libass, fall back to the first
    binary that merely exists (so cut/concat without burn-in still works).
    Finally default to the string "ffmpeg".
    """
    cands: list[str] = []
    if preferred:
        cands.append(preferred)
    cands.append("ffmpeg")
    cands.extend(candidates if candidates is not None else CANDIDATE_PATHS)

    # Prefer the first existing binary that supports libass.
    for c in cands:
        exe = _which(c)
        if exe and has_libass_fn(exe):
            return exe
    # Otherwise the first one that exists at all.
    for c in cands:
        exe = _which(c)
        if exe:
            return exe
    return "ffmpeg"
