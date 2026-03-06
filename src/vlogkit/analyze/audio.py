"""Audio analysis — volume, silence detection, peaks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..models import AudioAnalysis


def analyze_audio(clip_path: Path) -> AudioAnalysis:
    # Use ffprobe to get audio volume stats
    cmd = [
        "ffmpeg", "-i", str(clip_path),
        "-af", "volumedetect",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    mean_volume = 0.0
    for line in stderr.split("\n"):
        if "mean_volume" in line:
            parts = line.split("mean_volume:")
            if len(parts) > 1:
                try:
                    mean_volume = float(parts[1].strip().replace("dB", "").strip())
                except ValueError:
                    pass

    # Detect silence
    silence_cmd = [
        "ffmpeg", "-i", str(clip_path),
        "-af", "silencedetect=noise=-30dB:d=1",
        "-f", "null", "-",
    ]
    silence_result = subprocess.run(silence_cmd, capture_output=True, text=True)
    silence_stderr = silence_result.stderr

    silence_segments: list[tuple[float, float]] = []
    silence_start: float | None = None
    for line in silence_stderr.split("\n"):
        if "silence_start:" in line:
            parts = line.split("silence_start:")
            if len(parts) > 1:
                try:
                    silence_start = float(parts[1].strip())
                except ValueError:
                    pass
        elif "silence_end:" in line and silence_start is not None:
            parts = line.split("silence_end:")
            if len(parts) > 1:
                try:
                    end_parts = parts[1].strip().split("|")
                    silence_end = float(end_parts[0].strip())
                    silence_segments.append((silence_start, silence_end))
                except ValueError:
                    pass
            silence_start = None

    has_speech = mean_volume > -40.0

    return AudioAnalysis(
        average_volume=mean_volume,
        has_speech=has_speech,
        silence_segments=silence_segments,
    )
