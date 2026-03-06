"""Scene detection via PySceneDetect + keyframe extraction."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..models import SceneSegment


def detect_scenes(
    clip_path: Path,
    threshold: float = 27.0,
) -> list[SceneSegment]:
    from scenedetect import open_video, SceneManager
    from scenedetect.detectors import ContentDetector

    video = open_video(str(clip_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold))
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()

    segments = []
    for start, end in scene_list:
        segments.append(SceneSegment(
            start=start.get_seconds(),
            end=end.get_seconds(),
        ))

    # If no scenes detected, treat entire clip as one scene
    if not segments:
        from ..analyze.metadata import extract_metadata
        meta = extract_metadata(clip_path)
        segments.append(SceneSegment(start=0.0, end=meta.duration))

    return segments


def extract_keyframe(
    clip_path: Path,
    timestamp: float,
    output_path: Path,
) -> Path:
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", str(clip_path),
        "-vframes", "1",
        "-q:v", "2",
        str(output_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path
