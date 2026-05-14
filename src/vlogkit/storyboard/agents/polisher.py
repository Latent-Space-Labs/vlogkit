"""Polisher agent: takes Director plan + Editor picks and emits the final Storyboard JSON."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ...llm.base import LLMBackend
from ...models import ClipAnalysis, Storyboard
from ..prompts import POLISHER_PROMPT, POLISHER_SYSTEM_PROMPT
from .base import AgentError, parse_json_response
from .director import DirectorPlan
from .editor import EditorAssignments


def _clip_metadata_for_prompt(analyses: list[ClipAnalysis]) -> str:
    """JSON array of clip metadata for the Polisher prompt."""
    items = [
        {
            "filename": a.metadata.filename,
            "duration": round(a.metadata.duration, 2),
            "fps": a.metadata.fps,
        }
        for a in analyses
    ]
    return json.dumps(items, indent=2)


def _resolve_clip_paths(storyboard: Storyboard, project_root: Path) -> Storyboard:
    """Rewrite each segment's clip_path from a bare filename to a full project-relative path."""
    for section in storyboard.sections:
        for segment in section.segments:
            name = Path(segment.clip_path).name
            candidate = project_root / name
            if candidate.exists():
                segment.clip_path = candidate
                continue
            matches = list(project_root.rglob(name))
            if matches:
                segment.clip_path = matches[0]
            # else: leave as-is; export step will surface the missing file
    return storyboard


def run(
    plan: DirectorPlan,
    assignments: EditorAssignments,
    analyses: list[ClipAnalysis],
    project_root: Path,
    backend: LLMBackend,
) -> Storyboard:
    """Produce the final Storyboard JSON. Resolves bare filenames to full paths."""
    prompt = POLISHER_PROMPT.format(
        director_plan_json=plan.model_dump_json(indent=2),
        editor_assignments_json=assignments.model_dump_json(indent=2),
        clip_metadata_json=_clip_metadata_for_prompt(analyses),
    )

    raw = backend.complete(prompt, system=POLISHER_SYSTEM_PROMPT)

    try:
        data = parse_json_response(raw)
    except (ValueError, json.JSONDecodeError) as e:
        raise AgentError(stage="polisher", reason=f"could not parse JSON: {e}") from e

    try:
        storyboard = Storyboard.model_validate(data)
    except ValidationError as e:
        raise AgentError(stage="polisher", reason=f"schema validation failed: {e}") from e

    return _resolve_clip_paths(storyboard, project_root)
