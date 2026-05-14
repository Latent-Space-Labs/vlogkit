"""Per-scene Murch scoring agent."""

from __future__ import annotations

import json
from typing import Mapping

from ..llm.base import LLMBackend
from ..models import MurchScore, SceneSegment
from .prompts import SCORING_PROMPT, SYSTEM_PROMPT
from .weights import DEFAULT_WEIGHTS, composite_score


class ScoringError(Exception):
    """Raised when an LLM response cannot be parsed into a MurchScore."""


def _strip_fence(text: str) -> str:
    """Remove a leading/trailing ```json ... ``` fence if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # drop first line (fence + maybe lang)
        lines = lines[1:]
        # drop trailing fence if present
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def score_scene(
    scene: SceneSegment,
    scene_index: int,
    scenes: list[SceneSegment],
    clip_filename: str,
    transcript_text: str,
    backend: LLMBackend,
    weights: Mapping[str, Mapping[str, float]] | None = None,
) -> MurchScore:
    """Score one scene by sending its context to the LLM and parsing the response."""
    weights_to_use = weights or DEFAULT_WEIGHTS

    prev_description = scenes[scene_index - 1].description if scene_index > 0 else ""
    next_description = scenes[scene_index + 1].description if scene_index + 1 < len(scenes) else ""

    prompt = SCORING_PROMPT.format(
        scene_index=scene_index,
        scene_count=len(scenes),
        clip_filename=clip_filename,
        start=scene.start,
        end=scene.end,
        duration=scene.end - scene.start,
        description=scene.description or "(no visual description)",
        tags=", ".join(scene.tags) if scene.tags else "(none)",
        transcript=transcript_text or "(no speech)",
        prev_description=prev_description or "(none)",
        next_description=next_description or "(none)",
    )

    raw = backend.complete(prompt, system=SYSTEM_PROMPT)
    cleaned = _strip_fence(raw)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ScoringError(f"could not parse JSON: {e}; raw response: {raw[:200]!r}") from e

    try:
        scene_type = data["scene_type"]
        dim_scores = {dim: float(data[dim]) for dim in ("aesthetic", "credibility", "impact", "memorability", "fun")}
    except (KeyError, TypeError, ValueError) as e:
        raise ScoringError(f"missing or invalid field in response: {e}; data: {data!r}") from e

    composite = composite_score(scene_type, dim_scores, weights_to_use)

    return MurchScore(
        scene_type=scene_type,
        aesthetic=dim_scores["aesthetic"],
        credibility=dim_scores["credibility"],
        impact=dim_scores["impact"],
        memorability=dim_scores["memorability"],
        fun=dim_scores["fun"],
        composite=composite,
        rationale=str(data.get("rationale", "")),
    )
