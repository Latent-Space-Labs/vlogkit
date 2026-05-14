# Plan 3 — Multi-agent storyboard pipeline (PR 3 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-shot `build_storyboard()` LLM call with a Director → Editor → Polisher pipeline. Existing CLI surface (`vlogkit storyboard -s STRATEGY -c "context"`) stays unchanged. Existing strategies become Director-level prompt hints. Uses `MurchScore` data from PR 2 to inform the Editor's selections; degrades gracefully when scores are absent. Adds a `POST /projects/:id/score` server endpoint for desktop integration.

**Architecture:** Three sequential LLM calls. Each agent owns its own prompt template, internal Pydantic schema for its output, and a single `run(...)` function. The orchestrator in `storyboard/builder.py` wraps the three calls in a try/except that falls back to `chronological_fallback` (existing) on any agent failure. Stage progress is printed via `rich.console`.

**Tech Stack:** Python 3.11+, pytest, pydantic, anthropic SDK (existing), typer (existing), FastAPI (existing).

**Spec reference:** [`docs/superpowers/specs/2026-05-13-murch-scoring-multi-agent-storyboard-design.md`](../specs/2026-05-13-murch-scoring-multi-agent-storyboard-design.md) §5 (multi-agent details), §6.4 (file layout), §6.5 (server endpoint), §8 PR 3.

---

## File map

**Create:**
- `src/vlogkit/storyboard/agents/__init__.py` — empty package init
- `src/vlogkit/storyboard/agents/base.py` — `AgentError` exception + `parse_json_response()` helper
- `src/vlogkit/storyboard/agents/director.py` — Director agent: `DirectorPlan` model + `run()`
- `src/vlogkit/storyboard/agents/editor.py` — Editor agent: `EditorAssignments` model + `run()`
- `src/vlogkit/storyboard/agents/polisher.py` — Polisher agent: `run()` returning canonical `Storyboard`
- `src/vlogkit/server/routes/score.py` — `POST /projects/{id}/score` route
- `tests/test_storyboard_agents.py` — unit tests for the three agents
- `tests/test_storyboard_builder.py` — orchestration + fallback tests
- `tests/server/test_score_route.py` — server endpoint test

**Modify:**
- `src/vlogkit/storyboard/prompts.py` — add `DIRECTOR_*`, `EDITOR_*`, `POLISHER_*` prompt templates (keep existing `STORYBOARD_PROMPT`/`STRATEGY_HINTS`/`SYSTEM_PROMPT` — `STRATEGY_HINTS` is still consumed by Director)
- `src/vlogkit/storyboard/builder.py` — rewrite `build_storyboard()` to orchestrate the three agents
- `src/vlogkit/server/app.py` — register the new score router

**Unchanged but referenced:**
- `src/vlogkit/storyboard/strategies.py` — `chronological_fallback` stays as the no-LLM fallback
- `src/vlogkit/cli.py` — the `storyboard` command keeps its existing flags
- `src/vlogkit/models.py` — `Storyboard`, `StoryboardSection`, `StoryboardSegment` are the canonical output shapes

---

## Task 1: Create `agents/` package + `base.py` with `AgentError` and JSON helper

**Files:**
- Create: `src/vlogkit/storyboard/agents/__init__.py`
- Create: `src/vlogkit/storyboard/agents/base.py`
- Create: `tests/test_storyboard_agents.py`

- [ ] **Step 1: Create the failing tests**

Create `tests/test_storyboard_agents.py`:

```python
"""Unit tests for the storyboard agents (Director / Editor / Polisher)."""

from __future__ import annotations

import pytest

from vlogkit.storyboard.agents.base import AgentError, parse_json_response


def test_agent_error_records_stage_and_reason():
    err = AgentError(stage="director", reason="missing field")
    assert err.stage == "director"
    assert err.reason == "missing field"
    assert "director" in str(err)
    assert "missing field" in str(err)


def test_parse_json_response_plain_json():
    raw = '{"title": "Test", "sections": []}'
    assert parse_json_response(raw) == {"title": "Test", "sections": []}


def test_parse_json_response_strips_json_fence():
    raw = '```json\n{"title": "Test"}\n```'
    assert parse_json_response(raw) == {"title": "Test"}


def test_parse_json_response_strips_unlabeled_fence():
    raw = '```\n{"title": "Test"}\n```'
    assert parse_json_response(raw) == {"title": "Test"}


def test_parse_json_response_raises_value_error_on_garbage():
    with pytest.raises(ValueError):
        parse_json_response("this is not json")
```

- [ ] **Step 2: Run to confirm fail**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_agents.py -v
```

Expected: `ModuleNotFoundError: No module named 'vlogkit.storyboard.agents'`.

- [ ] **Step 3: Create the package init**

`src/vlogkit/storyboard/agents/__init__.py`:

```python
"""Storyboard agents: Director, Editor, Polisher."""
```

- [ ] **Step 4: Create `base.py`**

`src/vlogkit/storyboard/agents/base.py`:

```python
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
```

- [ ] **Step 5: Run tests to verify pass**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_agents.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/vlogkit/storyboard/agents/__init__.py src/vlogkit/storyboard/agents/base.py tests/test_storyboard_agents.py
git commit -m "$(cat <<'EOF'
feat(storyboard): add agents/ package with AgentError and JSON helper

Lays the foundation for the Director/Editor/Polisher pipeline.
AgentError carries a stage name so the orchestrator can name the
failing stage in its fallback warning. parse_json_response handles
both plain JSON and markdown-fenced responses.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add per-agent prompt templates to `storyboard/prompts.py`

**Files:**
- Modify: `src/vlogkit/storyboard/prompts.py`

- [ ] **Step 1: Read the existing file**

Confirm `src/vlogkit/storyboard/prompts.py` currently contains `SYSTEM_PROMPT`, `STORYBOARD_PROMPT`, and `STRATEGY_HINTS`.

- [ ] **Step 2: Append the three new prompts**

Add to the end of `src/vlogkit/storyboard/prompts.py`:

```python


# ----- Director agent -----

DIRECTOR_SYSTEM_PROMPT = """\
You are the Director planning a vlog's narrative arc.

You see scene-type counts in aggregate (not individual scenes) plus the user's \
context and chosen strategy. You decide the section structure: titles, goals, \
target durations, and which scene types each section needs.

Return strict JSON only — no markdown, no preamble."""

DIRECTOR_PROMPT = """\
Project context: "{context}"
Strategy hint: {strategy_hint}

Available material across {clip_count} clip(s) with {scene_count} total scene(s):
- Scene types available: {scene_type_summary}
- Clip summaries (first 100 chars each):
{clip_summaries}

Plan the section structure. Return JSON exactly matching:
{{
  "title": "string",
  "sections": [
    {{
      "id": "s1",
      "title": "string",
      "goal": "string — what this section accomplishes",
      "target_duration": 30,
      "scene_types": ["hook", "narrative", "aesthetic", "commercial"]
    }}
  ],
  "arc_rationale": "string — why this shape works"
}}

Keep total target_duration realistic relative to total available footage. \
Each section should request scene_types that exist in the available material."""


# ----- Editor agent -----

EDITOR_SYSTEM_PROMPT = """\
You are the Editor selecting which scenes fill each section of a planned arc.

You see the Director's section plan and a list of scored scenes. Pick scenes \
that match each section's requested scene_types, prefer higher composite \
scores, and aim for the target_duration (±25%). Return strict JSON only."""

EDITOR_PROMPT = """\
Director's plan:
{director_plan_json}

Available scenes (each with composite score and scene type):
{scenes_json}

Pick scenes for each section. Return JSON exactly matching:
{{
  "assignments": [
    {{
      "section_id": "s1",
      "picks": [
        {{
          "clip_path": "filename.mp4",
          "scene_index": 0,
          "in_point": 0.0,
          "out_point": 5.0,
          "reason": "short justification"
        }}
      ]
    }}
  ]
}}

Rules:
- in_point and out_point must lie within the scene's [start, end] range
- prefer scenes whose scene_type matches one of the section's scene_types
- prefer higher composite scores
- avoid back-to-back picks from the same clip unless explicitly justified in `reason`"""


# ----- Polisher agent -----

POLISHER_SYSTEM_PROMPT = """\
You are the Polisher finalizing the storyboard for export to a NLE.

You see the Director plan and Editor assignments. Add transitions, write \
viewer-facing labels, compute total duration, and provide an editorial \
rationale. Return strict JSON only — this is the final shape consumed by \
the export step."""

POLISHER_PROMPT = """\
Director plan:
{director_plan_json}

Editor assignments:
{editor_assignments_json}

Clip metadata (filename, duration, fps):
{clip_metadata_json}

Produce the final Storyboard. Return JSON exactly matching:
{{
  "title": "string",
  "sections": [
    {{
      "title": "string",
      "notes": "string",
      "segments": [
        {{
          "clip_path": "string (filename)",
          "in_point": 0.0,
          "out_point": 0.0,
          "label": "viewer-facing one-line description",
          "transition": "cut|dissolve|fade",
          "include": true
        }}
      ]
    }}
  ],
  "total_duration": 0.0,
  "llm_rationale": "string — short editorial summary"
}}

Transition rules:
- aesthetic→narrative often "dissolve"
- hook→narrative often "cut"
- narrative→aesthetic often "dissolve"
- otherwise default to "cut"
Mark `include: false` only if a pick is redundant or contradicts the section goal."""
```

- [ ] **Step 3: Verify imports work**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -c "
from vlogkit.storyboard.prompts import (
    DIRECTOR_PROMPT, DIRECTOR_SYSTEM_PROMPT,
    EDITOR_PROMPT, EDITOR_SYSTEM_PROMPT,
    POLISHER_PROMPT, POLISHER_SYSTEM_PROMPT,
    STORYBOARD_PROMPT, STRATEGY_HINTS, SYSTEM_PROMPT,
)
print('All prompts import cleanly.')
"
```

Expected: prints "All prompts import cleanly." with no exception.

- [ ] **Step 4: Commit**

```bash
git add src/vlogkit/storyboard/prompts.py
git commit -m "$(cat <<'EOF'
feat(storyboard): add Director/Editor/Polisher prompt templates

Three new system+user prompt pairs for the multi-agent pipeline.
Director sees aggregate scene-type counts and plans section structure.
Editor sees scored scenes and picks per section. Polisher emits the
final Storyboard JSON with transitions and labels. Existing
STORYBOARD_PROMPT and STRATEGY_HINTS remain — STRATEGY_HINTS will be
consumed by the Director.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Director agent

**Files:**
- Create: `src/vlogkit/storyboard/agents/director.py`
- Modify: `tests/test_storyboard_agents.py`

- [ ] **Step 1: Append the failing tests**

Add to `tests/test_storyboard_agents.py`:

```python
def test_director_run_parses_valid_response():
    from vlogkit.config import Settings
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
    from vlogkit.storyboard.agents.director import DirectorPlan, run

    captured_prompts: list[str] = []

    class FakeBackend:
        def complete(self, prompt: str, system: str = "") -> str:
            captured_prompts.append(prompt)
            return '{"title": "Hot Open", "sections": [{"id": "s1", "title": "Open", "goal": "tease", "target_duration": 8, "scene_types": ["hook"]}], "arc_rationale": "starts strong"}'

    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[
            SceneSegment(start=0, end=5, murch=MurchScore(
                scene_type="hook", aesthetic=80, credibility=80, impact=80,
                memorability=80, fun=80, composite=80,
            )),
            SceneSegment(start=5, end=10, murch=MurchScore(
                scene_type="narrative", aesthetic=50, credibility=50, impact=50,
                memorability=50, fun=50, composite=50,
            )),
        ],
        summary="a fun morning",
        file_hash="x",
    )

    plan = run(
        analyses=[analysis],
        strategy="energy-arc",
        context="a recent trip",
        backend=FakeBackend(),
    )
    assert isinstance(plan, DirectorPlan)
    assert plan.title == "Hot Open"
    assert len(plan.sections) == 1
    assert plan.sections[0].id == "s1"
    assert plan.sections[0].scene_types == ["hook"]

    # Verify the prompt mentions the strategy hint and scene-type counts
    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    assert "energy-arc" in prompt or "energy arc" in prompt.lower()
    assert "hook" in prompt and "narrative" in prompt


def test_director_run_handles_scenes_without_murch():
    """When scenes lack MurchScore, scene-type counts default to 'unknown'."""
    from vlogkit.models import ClipAnalysis, ClipMetadata, SceneSegment
    from vlogkit.storyboard.agents.director import run

    captured_prompts: list[str] = []

    class FakeBackend:
        def complete(self, prompt: str, system: str = "") -> str:
            captured_prompts.append(prompt)
            return '{"title": "T", "sections": [], "arc_rationale": "r"}'

    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[SceneSegment(start=0, end=5), SceneSegment(start=5, end=10)],
        file_hash="x",
    )

    run(analyses=[analysis], strategy="chronological", context="trip", backend=FakeBackend())

    assert "unknown" in captured_prompts[0]


def test_director_run_raises_agent_error_on_malformed_json():
    from vlogkit.models import ClipAnalysis, ClipMetadata
    from vlogkit.storyboard.agents.base import AgentError
    from vlogkit.storyboard.agents.director import run

    class FakeBackend:
        def complete(self, prompt, system=""):
            return "this is not json"

    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        file_hash="x",
    )

    with pytest.raises(AgentError) as exc:
        run(analyses=[analysis], strategy="energy-arc", context="trip", backend=FakeBackend())
    assert exc.value.stage == "director"


def test_director_run_raises_agent_error_on_missing_fields():
    from vlogkit.models import ClipAnalysis, ClipMetadata
    from vlogkit.storyboard.agents.base import AgentError
    from vlogkit.storyboard.agents.director import run

    class FakeBackend:
        def complete(self, prompt, system=""):
            return '{"title": "ok"}'  # missing sections + arc_rationale

    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        file_hash="x",
    )

    with pytest.raises(AgentError):
        run(analyses=[analysis], strategy="energy-arc", context="trip", backend=FakeBackend())
```

- [ ] **Step 2: Run to confirm fail**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_agents.py -v
```

Expected: new Director tests fail with `ModuleNotFoundError`.

- [ ] **Step 3: Create `src/vlogkit/storyboard/agents/director.py`**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_agents.py -v
```

Expected: 9 passed (5 base + 4 director).

- [ ] **Step 5: Commit**

```bash
git add src/vlogkit/storyboard/agents/director.py tests/test_storyboard_agents.py
git commit -m "$(cat <<'EOF'
feat(storyboard): add Director agent

The Director sees aggregate scene-type counts and clip summaries (not
individual scenes) plus the user's chosen strategy and context. It
returns a DirectorPlan with section ids, titles, goals, target durations,
and which scene types each section should be filled with. Scenes
without MurchScore are counted as "unknown".

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Editor agent

**Files:**
- Create: `src/vlogkit/storyboard/agents/editor.py`
- Modify: `tests/test_storyboard_agents.py`

- [ ] **Step 1: Append the failing tests**

```python
def test_editor_run_parses_valid_response():
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
    from vlogkit.storyboard.agents.director import DirectorPlan, DirectorSection
    from vlogkit.storyboard.agents.editor import EditorAssignments, run

    class FakeBackend:
        def complete(self, prompt, system=""):
            return '{"assignments": [{"section_id": "s1", "picks": [{"clip_path": "clip.mp4", "scene_index": 0, "in_point": 0.0, "out_point": 5.0, "reason": "best hook"}]}]}'

    plan = DirectorPlan(
        title="T",
        sections=[DirectorSection(id="s1", title="Open", goal="tease", target_duration=5, scene_types=["hook"])],
    )
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[SceneSegment(start=0, end=5, murch=MurchScore(
            scene_type="hook", aesthetic=80, credibility=80, impact=80,
            memorability=80, fun=80, composite=80,
        ))],
        file_hash="x",
    )

    assignments = run(plan=plan, analyses=[analysis], backend=FakeBackend())
    assert isinstance(assignments, EditorAssignments)
    assert len(assignments.assignments) == 1
    assert assignments.assignments[0].section_id == "s1"
    assert assignments.assignments[0].picks[0].clip_path == "clip.mp4"
    assert assignments.assignments[0].picks[0].in_point == 0.0
    assert assignments.assignments[0].picks[0].out_point == 5.0


def test_editor_run_clamps_in_out_points_to_scene_bounds():
    """If the LLM picks in/out points outside the scene's range, the orchestrator clamps them."""
    from vlogkit.models import ClipAnalysis, ClipMetadata, SceneSegment
    from vlogkit.storyboard.agents.director import DirectorPlan, DirectorSection
    from vlogkit.storyboard.agents.editor import run

    class FakeBackend:
        def complete(self, prompt, system=""):
            # LLM picks in_point=99 (beyond scene end of 5) and out_point=100
            return '{"assignments": [{"section_id": "s1", "picks": [{"clip_path": "clip.mp4", "scene_index": 0, "in_point": 99.0, "out_point": 100.0, "reason": "out of bounds"}]}]}'

    plan = DirectorPlan(
        title="T",
        sections=[DirectorSection(id="s1", title="Open", goal="tease", target_duration=5, scene_types=["hook"])],
    )
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path="/tmp/clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[SceneSegment(start=0, end=5)],
        file_hash="x",
    )

    assignments = run(plan=plan, analyses=[analysis], backend=FakeBackend())
    pick = assignments.assignments[0].picks[0]
    # Both points clamped to the scene's [0, 5] range
    assert 0 <= pick.in_point <= 5
    assert 0 <= pick.out_point <= 5
    assert pick.in_point <= pick.out_point


def test_editor_run_raises_agent_error_on_malformed_json():
    from vlogkit.storyboard.agents.base import AgentError
    from vlogkit.storyboard.agents.director import DirectorPlan
    from vlogkit.storyboard.agents.editor import run

    class FakeBackend:
        def complete(self, prompt, system=""):
            return "garbage"

    with pytest.raises(AgentError) as exc:
        run(plan=DirectorPlan(title="T"), analyses=[], backend=FakeBackend())
    assert exc.value.stage == "editor"
```

- [ ] **Step 2: Run to confirm fail**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_agents.py -v
```

Expected: new editor tests fail with ModuleNotFoundError.

- [ ] **Step 3: Create `src/vlogkit/storyboard/agents/editor.py`**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_agents.py -v
```

Expected: 12 passed (5 base + 4 director + 3 editor).

- [ ] **Step 5: Commit**

```bash
git add src/vlogkit/storyboard/agents/editor.py tests/test_storyboard_agents.py
git commit -m "$(cat <<'EOF'
feat(storyboard): add Editor agent

The Editor takes the Director's section plan plus a list of scored
scenes and picks scenes per section. After parsing, the orchestrator
clamps in/out points to lie within each source scene's [start, end]
range — defensive against the LLM picking out-of-bounds values.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Polisher agent

**Files:**
- Create: `src/vlogkit/storyboard/agents/polisher.py`
- Modify: `tests/test_storyboard_agents.py`

- [ ] **Step 1: Append the failing tests**

```python
def test_polisher_run_returns_canonical_storyboard(tmp_path):
    from vlogkit.models import ClipAnalysis, ClipMetadata, Storyboard
    from vlogkit.storyboard.agents.director import DirectorPlan, DirectorSection
    from vlogkit.storyboard.agents.editor import (
        EditorAssignments, EditorPick, EditorSectionAssignment,
    )
    from vlogkit.storyboard.agents.polisher import run

    class FakeBackend:
        def complete(self, prompt, system=""):
            return (
                '{"title": "Final Title", "sections": [{"title": "Open", "notes": "n", '
                '"segments": [{"clip_path": "clip.mp4", "in_point": 0.0, "out_point": 5.0, '
                '"label": "opening shot", "transition": "cut", "include": true}]}], '
                '"total_duration": 5.0, "llm_rationale": "tight"}'
            )

    plan = DirectorPlan(
        title="T",
        sections=[DirectorSection(id="s1", title="Open", goal="tease", target_duration=5)],
    )
    assignments = EditorAssignments(
        assignments=[EditorSectionAssignment(
            section_id="s1",
            picks=[EditorPick(clip_path="clip.mp4", scene_index=0, in_point=0.0, out_point=5.0, reason="ok")],
        )],
    )
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path=tmp_path / "clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        file_hash="x",
    )

    storyboard = run(
        plan=plan, assignments=assignments, analyses=[analysis],
        project_root=tmp_path, backend=FakeBackend(),
    )
    assert isinstance(storyboard, Storyboard)
    assert storyboard.title == "Final Title"
    assert len(storyboard.sections) == 1
    assert len(storyboard.sections[0].segments) == 1
    seg = storyboard.sections[0].segments[0]
    assert seg.label == "opening shot"
    assert seg.transition == "cut"
    assert seg.include is True


def test_polisher_run_resolves_clip_path_to_full_path(tmp_path):
    """Polisher rewrites bare filenames to project-relative paths so export can find them."""
    from vlogkit.models import ClipAnalysis, ClipMetadata
    from vlogkit.storyboard.agents.director import DirectorPlan, DirectorSection
    from vlogkit.storyboard.agents.editor import (
        EditorAssignments, EditorPick, EditorSectionAssignment,
    )
    from vlogkit.storyboard.agents.polisher import run

    # Create a real file the resolver can find
    (tmp_path / "clip.mp4").write_bytes(b"x")

    class FakeBackend:
        def complete(self, prompt, system=""):
            return (
                '{"title": "T", "sections": [{"title": "S", "notes": "", '
                '"segments": [{"clip_path": "clip.mp4", "in_point": 0.0, "out_point": 5.0, '
                '"label": "x", "transition": "cut", "include": true}]}], '
                '"total_duration": 5.0, "llm_rationale": "ok"}'
            )

    plan = DirectorPlan(
        title="T",
        sections=[DirectorSection(id="s1", title="S", goal="g", target_duration=5)],
    )
    assignments = EditorAssignments()
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path=tmp_path / "clip.mp4", duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        file_hash="x",
    )

    storyboard = run(
        plan=plan, assignments=assignments, analyses=[analysis],
        project_root=tmp_path, backend=FakeBackend(),
    )
    seg = storyboard.sections[0].segments[0]
    assert (tmp_path / "clip.mp4").samefile(seg.clip_path)


def test_polisher_run_raises_agent_error_on_malformed_json(tmp_path):
    from vlogkit.storyboard.agents.base import AgentError
    from vlogkit.storyboard.agents.director import DirectorPlan
    from vlogkit.storyboard.agents.editor import EditorAssignments
    from vlogkit.storyboard.agents.polisher import run

    class FakeBackend:
        def complete(self, prompt, system=""):
            return "junk"

    with pytest.raises(AgentError) as exc:
        run(
            plan=DirectorPlan(title="T"), assignments=EditorAssignments(),
            analyses=[], project_root=tmp_path, backend=FakeBackend(),
        )
    assert exc.value.stage == "polisher"
```

- [ ] **Step 2: Run to confirm fail**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_agents.py -v
```

Expected: new polisher tests fail with ModuleNotFoundError.

- [ ] **Step 3: Create `src/vlogkit/storyboard/agents/polisher.py`**

```python
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
```

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_agents.py -v
```

Expected: 15 passed (5 base + 4 director + 3 editor + 3 polisher).

- [ ] **Step 5: Commit**

```bash
git add src/vlogkit/storyboard/agents/polisher.py tests/test_storyboard_agents.py
git commit -m "$(cat <<'EOF'
feat(storyboard): add Polisher agent

The Polisher takes the Director plan + Editor assignments and emits
the canonical Storyboard JSON with transitions, viewer-facing labels,
total duration, and editorial rationale. After parsing, bare clip
filenames are resolved to project-relative paths so export can find
the source files.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Refactor `storyboard/builder.py` to orchestrate the three agents

**Files:**
- Modify: `src/vlogkit/storyboard/builder.py`
- Create: `tests/test_storyboard_builder.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_storyboard_builder.py`:

```python
"""Orchestration tests for the multi-agent storyboard pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest


def _make_analysis(filename: str = "clip.mp4", path_str: str = "/tmp/clip.mp4"):
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment

    return ClipAnalysis(
        metadata=ClipMetadata(
            filename=filename, path=Path(path_str), duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[
            SceneSegment(start=0, end=5, murch=MurchScore(
                scene_type="hook", aesthetic=80, credibility=80, impact=80,
                memorability=80, fun=80, composite=80,
            )),
        ],
        file_hash="x",
    )


def test_build_storyboard_no_api_key_uses_chronological_fallback(tmp_path):
    from vlogkit.config import Settings
    from vlogkit.storyboard.builder import build_storyboard

    sb = build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key=""),
        strategy="energy-arc",
        context="trip",
    )
    # chronological_fallback labels the section "All Clips (Chronological)"
    assert sb.sections[0].title == "All Clips (Chronological)"


def test_build_storyboard_runs_all_three_agents(tmp_path, monkeypatch):
    """Happy path: Director → Editor → Polisher are called in order with the right data."""
    from vlogkit.config import Settings
    from vlogkit.models import Storyboard, StoryboardSection, StoryboardSegment
    from vlogkit.storyboard import builder as builder_module
    from vlogkit.storyboard.agents.director import DirectorPlan
    from vlogkit.storyboard.agents.editor import EditorAssignments

    call_order: list[str] = []

    def fake_director_run(**kwargs):
        call_order.append("director")
        return DirectorPlan(title="From Director", sections=[])

    def fake_editor_run(**kwargs):
        call_order.append("editor")
        assert kwargs["plan"].title == "From Director"
        return EditorAssignments(assignments=[])

    def fake_polisher_run(**kwargs):
        call_order.append("polisher")
        assert kwargs["plan"].title == "From Director"
        return Storyboard(
            title="Final",
            sections=[StoryboardSection(
                title="S",
                segments=[StoryboardSegment(
                    clip_path=Path("/tmp/clip.mp4"), in_point=0, out_point=5,
                    label="x", transition="cut", include=True,
                )],
            )],
            total_duration=5.0,
            llm_rationale="ok",
        )

    monkeypatch.setattr("vlogkit.storyboard.builder.director.run", fake_director_run)
    monkeypatch.setattr("vlogkit.storyboard.builder.editor.run", fake_editor_run)
    monkeypatch.setattr("vlogkit.storyboard.builder.polisher.run", fake_polisher_run)

    sb = builder_module.build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key="test-key"),
        strategy="energy-arc",
        context="trip",
    )
    assert call_order == ["director", "editor", "polisher"]
    assert sb.title == "Final"


def test_build_storyboard_director_failure_falls_back_to_chronological(tmp_path, monkeypatch):
    from vlogkit.config import Settings
    from vlogkit.storyboard import builder as builder_module
    from vlogkit.storyboard.agents.base import AgentError

    def fake_director_run(**kwargs):
        raise AgentError(stage="director", reason="oops")

    monkeypatch.setattr("vlogkit.storyboard.builder.director.run", fake_director_run)

    sb = builder_module.build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key="test-key"),
        strategy="energy-arc",
        context="trip",
    )
    # Fallback used
    assert sb.sections[0].title == "All Clips (Chronological)"


def test_build_storyboard_editor_failure_falls_back(tmp_path, monkeypatch):
    from vlogkit.config import Settings
    from vlogkit.storyboard import builder as builder_module
    from vlogkit.storyboard.agents.base import AgentError
    from vlogkit.storyboard.agents.director import DirectorPlan

    monkeypatch.setattr(
        "vlogkit.storyboard.builder.director.run",
        lambda **kwargs: DirectorPlan(title="ok", sections=[]),
    )
    monkeypatch.setattr(
        "vlogkit.storyboard.builder.editor.run",
        lambda **kwargs: (_ for _ in ()).throw(AgentError(stage="editor", reason="oops")),
    )

    sb = builder_module.build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key="test-key"),
        strategy="energy-arc",
        context="trip",
    )
    assert sb.sections[0].title == "All Clips (Chronological)"


def test_build_storyboard_polisher_failure_falls_back(tmp_path, monkeypatch):
    from vlogkit.config import Settings
    from vlogkit.storyboard import builder as builder_module
    from vlogkit.storyboard.agents.base import AgentError
    from vlogkit.storyboard.agents.director import DirectorPlan
    from vlogkit.storyboard.agents.editor import EditorAssignments

    monkeypatch.setattr(
        "vlogkit.storyboard.builder.director.run",
        lambda **kwargs: DirectorPlan(title="ok", sections=[]),
    )
    monkeypatch.setattr(
        "vlogkit.storyboard.builder.editor.run",
        lambda **kwargs: EditorAssignments(),
    )
    monkeypatch.setattr(
        "vlogkit.storyboard.builder.polisher.run",
        lambda **kwargs: (_ for _ in ()).throw(AgentError(stage="polisher", reason="oops")),
    )

    sb = builder_module.build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key="test-key"),
        strategy="energy-arc",
        context="trip",
    )
    assert sb.sections[0].title == "All Clips (Chronological)"
```

- [ ] **Step 2: Run to confirm fail**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_builder.py -v
```

Expected: tests fail because `build_storyboard` doesn't yet import the agent modules with the names the monkeypatches expect.

- [ ] **Step 3: Replace `src/vlogkit/storyboard/builder.py`**

Replace the entire contents of `src/vlogkit/storyboard/builder.py` with:

```python
"""Build a storyboard via the Director → Editor → Polisher multi-agent pipeline."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from ..config import Settings
from ..llm.claude import ClaudeBackend
from ..models import ClipAnalysis, Storyboard
from .agents import director, editor, polisher
from .agents.base import AgentError
from .strategies import chronological_fallback

console = Console()


def build_storyboard(
    analyses: list[ClipAnalysis],
    project_root: Path,
    settings: Settings,
    strategy: str = "energy-arc",
    context: str = "a recent trip",
) -> Storyboard:
    """Generate a storyboard via the multi-agent pipeline.

    No API key → chronological fallback (no LLM).
    Any agent failure → chronological fallback with a warning naming the stage.
    """
    if not settings.anthropic_api_key:
        console.print("[yellow]No API key found. Using chronological fallback.[/]")
        return chronological_fallback(analyses)

    backend = ClaudeBackend(settings)
    backend.model = settings.storyboard_model

    try:
        console.print("[cyan]Director: planning narrative arc...[/]")
        plan = director.run(
            analyses=analyses, strategy=strategy, context=context, backend=backend,
        )

        console.print("[cyan]Editor: selecting scenes...[/]")
        assignments = editor.run(plan=plan, analyses=analyses, backend=backend)

        console.print("[cyan]Polisher: finalizing transitions and labels...[/]")
        storyboard = polisher.run(
            plan=plan, assignments=assignments, analyses=analyses,
            project_root=project_root, backend=backend,
        )

        console.print(
            f"[green]Storyboard created: {len(storyboard.sections)} section(s).[/]"
        )
        return storyboard

    except AgentError as e:
        console.print(
            f"[yellow]Multi-agent flow failed at stage '{e.stage}': {e.reason}. "
            f"Falling back to chronological order.[/]"
        )
        return chronological_fallback(analyses)
```

- [ ] **Step 4: Add `storyboard_model` to Settings**

In `src/vlogkit/config.py`, add a new setting right after `score_model`:

```python
    score_model: str = "claude-sonnet-4-20250514"  # VLOGKIT_SCORE_MODEL
    storyboard_model: str = "claude-sonnet-4-20250514"  # VLOGKIT_STORYBOARD_MODEL
```

- [ ] **Step 5: Run all tests**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_builder.py tests/test_storyboard_agents.py -v
```

Expected: 5 builder tests + 15 agent tests = 20 passed.

- [ ] **Step 6: Commit**

```bash
git add src/vlogkit/storyboard/builder.py src/vlogkit/config.py tests/test_storyboard_builder.py
git commit -m "$(cat <<'EOF'
feat(storyboard): replace single-shot LLM call with Director→Editor→Polisher pipeline

build_storyboard now orchestrates three sequential agent calls. Each
agent owns its prompt, schema, and run() function. AgentError at any
stage triggers chronological_fallback with a warning naming the failing
stage. The CLI surface (vlogkit storyboard -s STRATEGY -c "context") is
unchanged — strategy hints are now consumed by the Director.

Adds storyboard_model setting (defaults to the Sonnet baseline) so the
storyboard agents can be tuned independently of analyze + score.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Add `POST /projects/{id}/score` server route

**Files:**
- Create: `src/vlogkit/server/routes/score.py`
- Modify: `src/vlogkit/server/app.py`
- Create: `tests/server/test_score_route.py`

- [ ] **Step 1: Read the existing server pattern**

Look at `src/vlogkit/server/routes/analyze.py` for the existing async/threaded pattern. Score is shorter — it can run synchronously. We'll keep it simple: a sync POST that returns 200 with the count of scenes scored.

- [ ] **Step 2: Write the failing test**

Create `tests/server/test_score_route.py`:

```python
"""Tests for POST /projects/{id}/score."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _make_client(tmp_path: Path, monkeypatch) -> tuple[TestClient, str]:
    """Build a test client for the desktop server with a one-project registry."""
    from vlogkit.server.app import create_desktop_app

    project_root = tmp_path / "p"
    project_root.mkdir()
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"p": str(project_root)}))

    token = "test-token"
    app = create_desktop_app(registry_path=registry, token=token)
    return TestClient(app), token


def test_score_route_calls_run_scoring(tmp_path, monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_scoring(project, force=False):
        captured["project_root"] = project.root
        captured["force"] = force
        return 7

    monkeypatch.setattr("vlogkit.score.scorer.run_scoring", fake_run_scoring)

    client, token = _make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/projects/p/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"scored": 7}
    assert captured["force"] is False


def test_score_route_force_query_param(tmp_path, monkeypatch):
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "vlogkit.score.scorer.run_scoring",
        lambda project, force=False: (captured.setdefault("force", force), 0)[1],
    )

    client, token = _make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/projects/p/score?force=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert captured["force"] is True


def test_score_route_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setattr("vlogkit.score.scorer.run_scoring", lambda **kw: 0)
    client, _token = _make_client(tmp_path, monkeypatch)
    resp = client.post("/projects/p/score")
    assert resp.status_code in (401, 403)


def test_score_route_unknown_project_returns_404(tmp_path, monkeypatch):
    client, token = _make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/projects/nonexistent/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 3: Run to confirm fail**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/test_score_route.py -v
```

Expected: 404 on the route (not registered yet).

- [ ] **Step 4: Create the route**

Create `src/vlogkit/server/routes/score.py`:

```python
"""POST /projects/{id}/score — runs Murch scoring synchronously."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from vlogkit.score.scorer import run_scoring
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail


def create_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/projects/{project_id}/score",
        status_code=status.HTTP_200_OK,
        dependencies=[Depends(require_token)],
        responses={404: {"model": ErrorDetail}},
    )
    async def start_score(
        project_id: str,
        force: bool = False,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> dict[str, int]:
        project = load_project(registry, project_id)
        scored = run_scoring(project, force=force)
        return {"scored": scored}

    return router
```

- [ ] **Step 5: Register the router in `src/vlogkit/server/app.py`**

Read the file to find where other routers are registered (look for `.include_router(` calls in the desktop app factory). Add the score router alongside the others. The existing pattern looks like:

```python
from vlogkit.server.routes import analyze as analyze_route
# ...
app.include_router(analyze_route.create_router())
```

Add the analogous lines for score:

```python
from vlogkit.server.routes import score as score_route
# ...
app.include_router(score_route.create_router())
```

(The exact location of these imports + include_router calls in `app.py` depends on its current structure — read the file and follow the existing pattern.)

- [ ] **Step 6: Run tests**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/test_score_route.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add src/vlogkit/server/routes/score.py src/vlogkit/server/app.py tests/server/test_score_route.py
git commit -m "$(cat <<'EOF'
feat(server): add POST /projects/{id}/score endpoint

Thin wrapper around score.scorer.run_scoring. Synchronous (scoring is
not as long as analyze; can be made async later if needed). Accepts
?force=true to re-score already-scored scenes. Returns {"scored": N}.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Verify nothing else broke

**Files:**
- None modified

- [ ] **Step 1: Run the whole test suite**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest 2>&1 | tail -30
```

Expected: all new agent + builder + score-route tests pass; pre-existing test failures (sentrysearch, pytest-asyncio, openapi snapshot) are unchanged. If the OpenAPI snapshot test now fails for a NEW reason (e.g. the score route changed the schema), that's not a regression — it's expected schema drift, and the test was already failing for unrelated reasons.

- [ ] **Step 2: If a regression is found, fix it inline and commit**

The most likely surprise: the existing `test_storyboard_*` files (if any) might mock the OLD `build_storyboard` internals differently. Check `tests/test_strategies.py` — `chronological_fallback` is still public-API stable, so it should still pass.

If a real regression is found, fix and commit:

```bash
git add <files>
git commit -m "$(cat <<'EOF'
fix(storyboard): preserve <description of fix>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Manual smoke test

- [ ] **Step 1: Reuse the smoke project from Plan 2 or create a fresh one**

```bash
SMOKE=/tmp/vlogkit-smoke-plan3-$(date +%s)
mkdir -p "$SMOKE"
ffmpeg -y -f lavfi -i "color=c=red:s=320x240:d=4,format=yuv420p" \
        -f lavfi -i "color=c=green:s=320x240:d=4,format=yuv420p" \
        -f lavfi -i "color=c=blue:s=320x240:d=4,format=yuv420p" \
        -filter_complex "[0:v][1:v][2:v]concat=n=3:v=1[v]" \
        -map "[v]" -c:v libx264 -pix_fmt yuv420p -t 12 \
        "$SMOKE/test_clip.mp4"
echo "$SMOKE" > /tmp/vlogkit-smoke-plan3.txt
```

- [ ] **Step 2: Run the full pipeline (no-vision since synthetic clip has no real content)**

```bash
SMOKE=$(cat /tmp/vlogkit-smoke-plan3.txt)
WORKTREE=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
PY=/Users/bryan/Code/lsl/vlogkit/.venv/bin/python
cd "$SMOKE"
PYTHONPATH="$WORKTREE/src" "$PY" -c "from vlogkit.cli import app; app()" init .
VLOGKIT_SEARCH_AUTO_INDEX=false PYTHONPATH="$WORKTREE/src" "$PY" -c "from vlogkit.cli import app; app()" analyze --no-vision --force
PYTHONPATH="$WORKTREE/src" "$PY" -c "from vlogkit.cli import app; app()" score
PYTHONPATH="$WORKTREE/src" "$PY" -c "from vlogkit.cli import app; app()" storyboard -s energy-arc -c "test"
```

Expected without API key: `analyze` populates 3 scenes; `score` warns no key + no-op; `storyboard` warns no key + falls back to chronological with 3 segments.

If API key is set in the environment, expected: `score` produces MurchScores; `storyboard` runs the multi-agent pipeline (Director → Editor → Polisher messages print) and produces a real Storyboard with sections + transitions.

- [ ] **Step 3: Inspect the generated storyboard**

```bash
cat .vlogkit/storyboard.json | head -50
```

Expected: a valid `Storyboard` JSON.

---

## Task 10: Open the PR + merge

- [ ] **Step 1: Push the branch**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
git push -u origin claude/plan-3-multiagent-storyboard
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "feat(storyboard): multi-agent Director→Editor→Polisher pipeline (PR 3 of 3)" --body "$(cat <<'EOF'
## Summary
- Replaces the single-shot `build_storyboard()` LLM call with a Director → Editor → Polisher pipeline.
- New `storyboard/agents/` package: `base.py` (AgentError + JSON helper), `director.py`, `editor.py`, `polisher.py`. Each agent owns its prompt, internal Pydantic schema, and a single `run()` function.
- Existing CLI surface unchanged: `vlogkit storyboard -s STRATEGY -c "context"` works identically. Strategies (`chronological`, `energy-arc`, `thematic`) become Director-level prompt hints.
- Editor uses MurchScore data from PR 2 to inform selections; degrades gracefully (counts missing scenes as `unknown`) when scores are absent.
- Any agent failure → falls back to `chronological_fallback` (existing) with a warning naming the failing stage.
- New server endpoint `POST /projects/{id}/score` for desktop-shell integration.
- New `storyboard_model` config setting.

This is **PR 3 of 3** — completes the Murch-scoring + multi-agent-storyboard rollout.

Spec: [`docs/superpowers/specs/2026-05-13-murch-scoring-multi-agent-storyboard-design.md`](docs/superpowers/specs/2026-05-13-murch-scoring-multi-agent-storyboard-design.md)
Plan: [`docs/superpowers/plans/2026-05-13-plan-3-multiagent-storyboard.md`](docs/superpowers/plans/2026-05-13-plan-3-multiagent-storyboard.md)

## Test plan
- [x] Agent unit tests (`tests/test_storyboard_agents.py`): 15 tests covering base helpers + each agent's parsing, error handling, and key behaviors (Director scene-type aggregation, Editor in/out clamping, Polisher path resolution)
- [x] Builder orchestration tests (`tests/test_storyboard_builder.py`): 5 tests covering happy path + per-stage fallback behavior
- [x] Server route tests (`tests/server/test_score_route.py`): 4 tests covering the new `POST /projects/{id}/score` endpoint
- [x] Manual smoke test against synthetic 3-scene ffmpeg clip
- [x] Full test suite: pre-existing failures unchanged, no new regressions

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist (do before declaring Plan 3 done)

- [ ] Every step has actual code / commands, no placeholders
- [ ] Internal types (DirectorPlan, EditorAssignments, EditorPick) are referenced consistently across agents and builder
- [ ] All `run(...)` signatures match between definition and callers (especially keyword args from builder.py)
- [ ] `monkeypatch.setattr("vlogkit.storyboard.builder.director.run", ...)` paths match where the names are bound (the builder imports `director` as a module, not the function directly)
- [ ] Each agent raises `AgentError(stage="...")` with the correct stage name
- [ ] Polisher's path resolution preserves backward compat — segments without a matching file leave `clip_path` unchanged
- [ ] Spec coverage: §5 (multi-agent details), §6.4 (file layout), §6.5 (server endpoint), §8 PR 3 — all addressed
- [ ] Commits are small, each focused on one logical change
