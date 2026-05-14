"""Editor agent: picks scenes for each section based on Director plan and scene scores."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError

from ...llm.base import LLMBackend
from ...models import ClipAnalysis
from ..prompts import EDITOR_PROMPT, EDITOR_SYSTEM_PROMPT
from .base import AgentError, parse_json_response
from .director import DirectorPlan


class EditorPick(BaseModel):
    clip_path: str
    scene_index: int
    in_point: float
    out_point: float
    reason: str = ""


class EditorSectionAssignment(BaseModel):
    section_id: str
    picks: list[EditorPick] = Field(default_factory=list)


class EditorAssignments(BaseModel):
    assignments: list[EditorSectionAssignment] = Field(default_factory=list)


def _scenes_summary_for_prompt(analyses: list[ClipAnalysis]) -> str:
    """Build a JSON array of scored scenes for the Editor's prompt."""
    items: list[dict] = []
    for a in analyses:
        for idx, scene in enumerate(a.scenes):
            entry: dict = {
                "clip_path": a.metadata.filename,
                "scene_index": idx,
                "start": round(scene.start, 2),
                "end": round(scene.end, 2),
                "duration": round(scene.end - scene.start, 2),
                "description": scene.description or "",
                "tags": scene.tags,
            }
            if scene.murch is not None:
                entry["scene_type"] = scene.murch.scene_type
                entry["composite"] = round(scene.murch.composite, 1)
            else:
                entry["scene_type"] = "unknown"
                entry["composite"] = None
            items.append(entry)
    return json.dumps(items, indent=2)


def _clamp_picks_to_scene_bounds(
    assignments: EditorAssignments, analyses: list[ClipAnalysis]
) -> EditorAssignments:
    """Force in/out points to lie within the source scene's [start, end] range."""
    by_filename: dict[str, ClipAnalysis] = {a.metadata.filename: a for a in analyses}
    for assignment in assignments.assignments:
        for pick in assignment.picks:
            analysis = by_filename.get(pick.clip_path)
            if analysis is None or pick.scene_index >= len(analysis.scenes):
                continue
            scene = analysis.scenes[pick.scene_index]
            pick.in_point = max(scene.start, min(pick.in_point, scene.end))
            pick.out_point = max(scene.start, min(pick.out_point, scene.end))
            if pick.in_point > pick.out_point:
                pick.in_point, pick.out_point = pick.out_point, pick.in_point
    return assignments


def run(
    plan: DirectorPlan,
    analyses: list[ClipAnalysis],
    backend: LLMBackend,
) -> EditorAssignments:
    """Pick scenes per section. Returns EditorAssignments with clamped in/out points."""
    prompt = EDITOR_PROMPT.format(
        director_plan_json=plan.model_dump_json(indent=2),
        scenes_json=_scenes_summary_for_prompt(analyses),
    )

    raw = backend.complete(prompt, system=EDITOR_SYSTEM_PROMPT)

    try:
        data = parse_json_response(raw)
    except (ValueError, json.JSONDecodeError) as e:
        raise AgentError(stage="editor", reason=f"could not parse JSON: {e}") from e

    try:
        assignments = EditorAssignments.model_validate(data)
    except ValidationError as e:
        raise AgentError(stage="editor", reason=f"schema validation failed: {e}") from e

    return _clamp_picks_to_scene_bounds(assignments, analyses)
