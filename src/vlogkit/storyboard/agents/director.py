"""Director agent: plans the section structure of the storyboard."""

from __future__ import annotations

import json
from collections import Counter

from pydantic import BaseModel, Field, ValidationError

from ...llm.base import LLMBackend
from ...models import ClipAnalysis
from ..prompts import DIRECTOR_PROMPT, DIRECTOR_SYSTEM_PROMPT, STRATEGY_HINTS
from .base import AgentError, parse_json_response


class DirectorSection(BaseModel):
    id: str
    title: str
    goal: str
    target_duration: float
    scene_types: list[str] = Field(default_factory=list)


class DirectorPlan(BaseModel):
    title: str
    sections: list[DirectorSection] = Field(default_factory=list)
    arc_rationale: str = ""


def _scene_type_summary(analyses: list[ClipAnalysis]) -> str:
    """Build a short string like 'hook: 3, narrative: 5, aesthetic: 7, unknown: 2'."""
    counter: Counter[str] = Counter()
    for a in analyses:
        for scene in a.scenes:
            if scene.murch is not None:
                counter[scene.murch.scene_type] += 1
            else:
                counter["unknown"] += 1
    if not counter:
        return "(no scenes)"
    return ", ".join(f"{k}: {v}" for k, v in sorted(counter.items()))


def _clip_summaries_text(analyses: list[ClipAnalysis]) -> str:
    """One line per clip: filename + first 100 chars of summary."""
    lines = []
    for a in analyses:
        summary = (a.summary or "").strip().replace("\n", " ")[:100]
        lines.append(f"  - {a.metadata.filename}: {summary or '(no summary)'}")
    return "\n".join(lines) if lines else "  (none)"


def run(
    analyses: list[ClipAnalysis],
    strategy: str,
    context: str,
    backend: LLMBackend,
) -> DirectorPlan:
    """Plan the section structure and return a DirectorPlan."""
    strategy_hint = STRATEGY_HINTS.get(strategy, STRATEGY_HINTS.get("energy-arc", ""))
    scene_count = sum(len(a.scenes) for a in analyses)

    prompt = DIRECTOR_PROMPT.format(
        context=context,
        strategy_hint=strategy_hint,
        clip_count=len(analyses),
        scene_count=scene_count,
        scene_type_summary=_scene_type_summary(analyses),
        clip_summaries=_clip_summaries_text(analyses),
    )

    raw = backend.complete(prompt, system=DIRECTOR_SYSTEM_PROMPT)

    try:
        data = parse_json_response(raw)
    except (ValueError, json.JSONDecodeError) as e:
        raise AgentError(stage="director", reason=f"could not parse JSON: {e}") from e

    try:
        return DirectorPlan.model_validate(data)
    except ValidationError as e:
        raise AgentError(stage="director", reason=f"schema validation failed: {e}") from e
