"""Describe keyframes via Claude vision API."""

from __future__ import annotations

from ..config import Settings
from ..llm.claude import ClaudeBackend


VISION_PROMPT = """\
Describe this video keyframe in 1-2 sentences for a video editor. \
Focus on: setting/location, people/action, mood/energy level, notable objects. \
Also suggest 3-5 short tags."""


def describe_keyframe(
    image_path: str,
    settings: Settings,
) -> tuple[str, list[str]]:
    backend = ClaudeBackend(settings)
    response = backend.complete_with_images(
        VISION_PROMPT,
        [image_path],
        system="You are a concise video editing assistant. Respond with a description line, then a comma-separated tags line prefixed with 'Tags: '.",
    )

    lines = response.strip().split("\n")
    description = lines[0] if lines else ""
    tags: list[str] = []
    for line in lines:
        if line.lower().startswith("tags:"):
            tags = [t.strip() for t in line.split(":", 1)[1].split(",")]
            break

    return description, tags
