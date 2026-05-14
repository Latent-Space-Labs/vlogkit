"""Shared types and helpers for storyboard agents."""

from __future__ import annotations

import json


class AgentError(Exception):
    """Raised when an agent stage fails to produce a valid output.

    The orchestrator catches this and falls back to chronological_fallback,
    using the stage name in the warning printed to the user.
    """

    def __init__(self, stage: str, reason: str):
        super().__init__(f"{stage}: {reason}")
        self.stage = stage
        self.reason = reason


def parse_json_response(raw: str) -> dict:
    """Parse a JSON object from an LLM response, tolerating ``` fences.

    Raises ValueError if the cleaned text is not valid JSON.
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
