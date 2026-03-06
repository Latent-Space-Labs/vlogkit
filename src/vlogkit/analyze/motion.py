"""Motion/energy scoring for clips."""

from __future__ import annotations

import subprocess
from pathlib import Path


def motion_score(clip_path: Path) -> float:
    """Estimate motion energy by measuring inter-frame difference via ffmpeg."""
    cmd = [
        "ffmpeg", "-i", str(clip_path),
        "-vf", "mpdecimate,metadata=print:file=-",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Count frames kept vs total — more kept = more motion
    lines = result.stderr.split("\n")
    total_frames = 0
    for line in lines:
        if "frame=" in line:
            parts = line.split("frame=")
            if len(parts) > 1:
                try:
                    total_frames = int(parts[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass

    # Rough heuristic: normalize to 0-1 range
    # This is a placeholder — Phase 2 will refine with proper optical flow
    return min(1.0, total_frames / 1000.0) if total_frames > 0 else 0.5
