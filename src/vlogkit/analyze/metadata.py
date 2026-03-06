"""Extract clip metadata via ffprobe."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

from ..models import ClipMetadata


def probe(clip_path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(clip_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def extract_metadata(clip_path: Path) -> ClipMetadata:
    info = probe(clip_path)

    video_stream = next(
        (s for s in info.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    fmt = info.get("format", {})

    duration = float(fmt.get("duration", 0))
    width = int(video_stream.get("width", 0)) if video_stream else 0
    height = int(video_stream.get("height", 0)) if video_stream else 0

    # Parse FPS from r_frame_rate like "30000/1001"
    fps = 0.0
    if video_stream:
        rfr = video_stream.get("r_frame_rate", "0/1")
        if "/" in rfr:
            num, den = rfr.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 0.0
        else:
            fps = float(rfr)

    creation_time = None
    tags = fmt.get("tags", {})
    ct = tags.get("creation_time") or (video_stream or {}).get("tags", {}).get("creation_time")
    if ct:
        try:
            creation_time = datetime.fromisoformat(ct.replace("Z", "+00:00"))
        except ValueError:
            pass

    codec = video_stream.get("codec_name") if video_stream else None

    return ClipMetadata(
        filename=clip_path.name,
        path=clip_path,
        duration=duration,
        resolution=(width, height),
        fps=round(fps, 3),
        creation_time=creation_time,
        file_size=clip_path.stat().st_size,
        codec=codec,
    )
