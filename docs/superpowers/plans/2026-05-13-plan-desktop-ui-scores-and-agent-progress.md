# Desktop UI for Murch Scores + Multi-Agent Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the Murch scoring + multi-agent storyboard pipeline (PRs #1-3) in the desktop renderer with a "Score scenes" button, color-tiered composite chips on clip cards, click-to-expand per-scene breakdown with type chips + 5-dim bars, a 3-step Director→Editor→Polisher progress banner during storyboard regenerate, and a Murch readout in the segment inspector.

**Architecture:** Backend converts the `score` endpoint sync→async (mirroring `analyze`), publishes new WS events (`score.*` + `storyboard.agent_*`), and exposes typed `analysis.scenes[].murch` in `ClipSummary`. Renderer adds 6 new components, extends the events reducer, and surfaces scores on clip cards + inspector.

**Tech Stack:** Python 3.11+, pytest, pydantic, FastAPI, Next.js 15, React 19, @tanstack/react-query, Tailwind CSS, openapi-typescript.

**Spec reference:** [`docs/superpowers/specs/2026-05-13-desktop-ui-scores-and-agent-progress-design.md`](../specs/2026-05-13-desktop-ui-scores-and-agent-progress-design.md)

---

## Conventions (read before starting)

**Event naming.** WS event types use dot-separator strings: `score.started`, `score.progress`, `storyboard.agent_started`. Server-side they are `Pydantic` models in `src/vlogkit/server/schemas.py` with a `Literal["..."]` discriminator on `type`. Renderer-side they are hand-typed in `desktop/web/src/lib/events.ts` (kept in sync manually because WS messages don't appear in OpenAPI).

**Renderer testing.** The renderer has **no test runner installed** (only `lint`). This plan does NOT add Vitest — that's scope creep and would slow the PR. Renderer changes are verified by:
1. `npm --prefix desktop/web run lint` (ESLint passes)
2. `npx --prefix desktop/web tsc --noEmit` (TypeScript typecheck passes)
3. The manual smoke test (Task 13)

Backend changes use full TDD cycles since pytest is already established.

**Type regeneration.** The renderer's `lib/api-types.ts` is generated from the running server's OpenAPI schema. The script:

```bash
# From repo root, with the server running on its default port
npx --prefix desktop/web openapi-typescript http://127.0.0.1:8421/openapi.json -o desktop/web/src/lib/api-types.ts
```

Or, against a saved snapshot (works without a running server):

```bash
PYTHONPATH=src .venv/bin/python -c "
from vlogkit.server.app import create_desktop_app
import json, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as t:
    reg = Path(t) / 'r.json'; reg.write_text('[]')
    app = create_desktop_app(registry_path=reg, token='x')
    schema = app.openapi()
    Path('/tmp/openapi.json').write_text(json.dumps(schema))
"
npx --prefix desktop/web openapi-typescript /tmp/openapi.json -o desktop/web/src/lib/api-types.ts
```

Use the snapshot approach in CI / from the agent — no live server required.

**Working directory:** `/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1` on branch `claude/desktop-ui-scores`. Use `/Users/bryan/Code/lsl/vlogkit/.venv/bin/python` for tests.

---

## File map

**Backend — Modify:**
- `src/vlogkit/server/schemas.py` — add `ScoreStarted`, `ScoreProgress`, `ScoreClipDone`, `ScoreComplete`, `ScoreFailed`, `StoryboardAgentStarted`, `StoryboardAgentComplete`, `StoryboardAgentFailed` event models; add `ClipScene`, `ClipMurchScore`, `ClipAnalysisSummary`; modify `ClipSummary.analysis` to typed
- `src/vlogkit/server/jobs.py` — add `run_score_job(broker, project_id, project, job_id, force)`
- `src/vlogkit/server/routes/score.py` — convert sync → async route, return `{"job_id": str}`
- `src/vlogkit/server/routes/clips.py` — adapter to populate `ClipAnalysisSummary` from internal `ClipAnalysis`
- `src/vlogkit/score/scorer.py` — `run_scoring` accepts optional `progress_callback` parameter
- `src/vlogkit/storyboard/builder.py` — `build_storyboard` accepts optional `event_callback` parameter

**Backend — Create:**
- `tests/server/test_score_job.py` — async score job + event emission
- `tests/server/test_score_route.py` — UPDATE (already exists from PR 3) — async response shape

**Renderer — Modify:**
- `desktop/web/src/lib/events.ts` — extend with `ScoreEvent` + `StoryboardAgentEvent` unions
- `desktop/web/src/lib/api.ts` — add `score()` method
- `desktop/web/src/lib/api-types.ts` — regenerate from updated OpenAPI
- `desktop/web/src/components/clips/clip-list.tsx` — add `<ScoreButton />` next to `<AnalyzeButton />`
- `desktop/web/src/components/clips/clip-card.tsx` — add composite chip + expand affordance + scene rows
- `desktop/web/src/components/board/board.tsx` — mount `<AgentProgressStepper />` during regenerate
- `desktop/web/src/components/board/inspector-drawer.tsx` — add Murch readout block

**Renderer — Create:**
- `desktop/web/src/components/clips/score-button.tsx`
- `desktop/web/src/components/clips/composite-chip.tsx`
- `desktop/web/src/components/clips/scene-type-chip.tsx`
- `desktop/web/src/components/clips/dimension-bar.tsx`
- `desktop/web/src/components/clips/scene-row.tsx`
- `desktop/web/src/components/board/agent-progress-stepper.tsx`

---

## Task 1: Add new event Pydantic models to `schemas.py`

**Files:**
- Modify: `src/vlogkit/server/schemas.py`
- Modify: `tests/server/test_openapi_snapshot.py` (only the snapshot regen step at the end — see Task 5)

- [ ] **Step 1: Write the failing test**

Create `tests/server/test_event_models.py`:

```python
"""Tests for new score and agent-stage event models."""

from __future__ import annotations

import pytest


def test_score_started_event_serializes_with_type_discriminator():
    from vlogkit.server.schemas import ScoreStarted

    evt = ScoreStarted(job_id="abc", total_scenes=24)
    dumped = evt.model_dump()
    assert dumped["type"] == "score.started"
    assert dumped["job_id"] == "abc"
    assert dumped["total_scenes"] == 24


def test_score_progress_event_fields():
    from vlogkit.server.schemas import ScoreProgress

    evt = ScoreProgress(
        job_id="abc", scored=3, total_scenes=10,
        current_clip="clip.mp4", current_scene_index=2,
    )
    dumped = evt.model_dump()
    assert dumped["type"] == "score.progress"
    assert dumped["scored"] == 3
    assert dumped["current_clip"] == "clip.mp4"


def test_score_clip_done_event_fields():
    from vlogkit.server.schemas import ScoreClipDone

    evt = ScoreClipDone(job_id="abc", clip_filename="clip.mp4", average_composite=78.5)
    dumped = evt.model_dump()
    assert dumped["type"] == "score.clip_done"
    assert dumped["average_composite"] == 78.5


def test_score_complete_event_fields():
    from vlogkit.server.schemas import ScoreComplete

    evt = ScoreComplete(job_id="abc", total_scored=24)
    assert evt.model_dump()["type"] == "score.complete"


def test_score_failed_event_fields():
    from vlogkit.server.schemas import ScoreFailed

    evt = ScoreFailed(job_id="abc", error="boom")
    assert evt.model_dump()["type"] == "score.failed"
    assert evt.model_dump()["error"] == "boom"


def test_storyboard_agent_started_event_fields():
    from vlogkit.server.schemas import StoryboardAgentStarted

    evt = StoryboardAgentStarted(job_id="abc", stage="director")
    dumped = evt.model_dump()
    assert dumped["type"] == "storyboard.agent_started"
    assert dumped["stage"] == "director"


def test_storyboard_agent_complete_event_fields():
    from vlogkit.server.schemas import StoryboardAgentComplete

    evt = StoryboardAgentComplete(job_id="abc", stage="editor", summary="Picked 12 segments")
    dumped = evt.model_dump()
    assert dumped["type"] == "storyboard.agent_complete"
    assert dumped["stage"] == "editor"
    assert dumped["summary"] == "Picked 12 segments"


def test_storyboard_agent_failed_event_fields():
    from vlogkit.server.schemas import StoryboardAgentFailed

    evt = StoryboardAgentFailed(job_id="abc", stage="polisher", reason="schema validation failed")
    dumped = evt.model_dump()
    assert dumped["type"] == "storyboard.agent_failed"
    assert dumped["reason"] == "schema validation failed"


def test_storyboard_agent_started_rejects_invalid_stage():
    import pytest
    from pydantic import ValidationError

    from vlogkit.server.schemas import StoryboardAgentStarted

    with pytest.raises(ValidationError):
        StoryboardAgentStarted(job_id="abc", stage="invalid")  # type: ignore[arg-type]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/test_event_models.py -v
```

Expected: ALL fail with `ImportError: cannot import name 'ScoreStarted' from 'vlogkit.server.schemas'` (and similar for the others).

- [ ] **Step 3: Add the event models to `src/vlogkit/server/schemas.py`**

Append to the END of `src/vlogkit/server/schemas.py` (don't modify existing models):

```python
# ---- Score job events (new) ----

class ScoreStarted(BaseModel):
    type: Literal["score.started"] = "score.started"
    job_id: str
    total_scenes: int


class ScoreProgress(BaseModel):
    type: Literal["score.progress"] = "score.progress"
    job_id: str
    scored: int
    total_scenes: int
    current_clip: str
    current_scene_index: int


class ScoreClipDone(BaseModel):
    type: Literal["score.clip_done"] = "score.clip_done"
    job_id: str
    clip_filename: str
    average_composite: float


class ScoreComplete(BaseModel):
    type: Literal["score.complete"] = "score.complete"
    job_id: str
    total_scored: int


class ScoreFailed(BaseModel):
    type: Literal["score.failed"] = "score.failed"
    job_id: str
    error: str


# ---- Storyboard multi-agent stage events (new) ----

AgentStage = Literal["director", "editor", "polisher"]


class StoryboardAgentStarted(BaseModel):
    type: Literal["storyboard.agent_started"] = "storyboard.agent_started"
    job_id: str
    stage: AgentStage


class StoryboardAgentComplete(BaseModel):
    type: Literal["storyboard.agent_complete"] = "storyboard.agent_complete"
    job_id: str
    stage: AgentStage
    summary: str = ""


class StoryboardAgentFailed(BaseModel):
    type: Literal["storyboard.agent_failed"] = "storyboard.agent_failed"
    job_id: str
    stage: AgentStage
    reason: str
```

The existing imports at the top of `schemas.py` should already include `BaseModel` and `Literal`. If `Literal` isn't imported yet, add it: `from typing import Literal` at the top.

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/test_event_models.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add src/vlogkit/server/schemas.py tests/server/test_event_models.py
git commit -m "$(cat <<'EOF'
feat(server): add score and storyboard agent event models

Adds 5 score.* event types (started/progress/clip_done/complete/failed)
and 3 storyboard.agent_* event types (started/complete/failed) as
typed Pydantic models in schemas.py with Literal[type] discriminators
matching the existing analyze.* and storyboard.regen_* patterns. These
are emitted by the score job (next task) and the storyboard regenerate
job (Task 3) so the renderer can drive the score progress UI and the
3-step agent stepper.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Convert `score` endpoint to async + add `run_score_job`

**Files:**
- Modify: `src/vlogkit/score/scorer.py` — add optional `progress_callback`
- Modify: `src/vlogkit/server/jobs.py` — add `run_score_job`
- Modify: `src/vlogkit/server/routes/score.py` — async response
- Modify: `tests/server/test_score_route.py` — update tests for new shape
- Create: `tests/server/test_score_job.py`

- [ ] **Step 1: Write failing test for `run_scoring(progress_callback=...)`**

Append to `tests/test_score.py`:

```python
def test_run_scoring_invokes_progress_callback_per_scene_and_per_clip(tmp_path, monkeypatch):
    from vlogkit.config import Settings
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
    from vlogkit.project import Project
    from vlogkit.score import scorer as scorer_module

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path=clip, duration=10.0, resolution=(1, 1), fps=30.0, file_size=4
        ),
        scenes=[SceneSegment(start=0, end=5), SceneSegment(start=5, end=10)],
        file_hash="x",
    )
    monkeypatch.setattr(Project, "scan_clips", lambda self: [clip])
    monkeypatch.setattr(Project, "load_analysis", lambda self, c: analysis)
    monkeypatch.setattr(Project, "save_analysis", lambda self, a: None)

    def fake_score_scene(scene, scene_index, **kwargs):
        return MurchScore(
            scene_type="narrative", aesthetic=50, credibility=50, impact=50,
            memorability=50, fun=50, composite=50.0,
        )

    monkeypatch.setattr(scorer_module, "score_scene", fake_score_scene)

    class FakeBackend:
        model = "fake"
        def complete(self, prompt, system=""):
            return ""
    monkeypatch.setattr("vlogkit.score.scorer.ClaudeBackend", lambda settings: FakeBackend())

    callback_calls: list[dict] = []

    def progress_callback(event_type: str, **kwargs):
        callback_calls.append({"type": event_type, **kwargs})

    project = Project(tmp_path, settings=Settings(anthropic_api_key="test-key", score_model="fake"))
    scorer_module.run_scoring(project, force=False, progress_callback=progress_callback)

    # Should have one "scene_scored" per scene + one "clip_done" per clip
    types = [c["type"] for c in callback_calls]
    assert types.count("scene_scored") == 2
    assert types.count("clip_done") == 1

    # Each scene_scored callback should include current_clip + current_scene_index
    scene_calls = [c for c in callback_calls if c["type"] == "scene_scored"]
    assert all("current_clip" in c for c in scene_calls)
    assert all("current_scene_index" in c for c in scene_calls)
    assert [c["current_scene_index"] for c in scene_calls] == [0, 1]

    # clip_done callback should include average_composite (50.0 since both scenes scored 50)
    clip_done = [c for c in callback_calls if c["type"] == "clip_done"][0]
    assert clip_done["clip_filename"] == "clip.mp4"
    assert clip_done["average_composite"] == 50.0
```

- [ ] **Step 2: Run to confirm fail**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_score.py::test_run_scoring_invokes_progress_callback_per_scene_and_per_clip -v
```

Expected: FAIL with `TypeError: run_scoring() got an unexpected keyword argument 'progress_callback'`.

- [ ] **Step 3: Modify `run_scoring` to accept `progress_callback`**

Open `src/vlogkit/score/scorer.py`. Find the existing `run_scoring` function and modify its signature + body. Replace the existing `run_scoring` function with this version (the rest of the file is unchanged):

```python
def run_scoring(
    project: Project,
    force: bool = False,
    progress_callback: callable | None = None,
) -> int:
    """Score every detected scene in the project; returns the count of scenes scored.

    progress_callback, if provided, is called with:
      - ("scene_scored", current_clip=str, current_scene_index=int, scored=int, total_scenes=int)
      - ("clip_done", clip_filename=str, average_composite=float)
    """
    if not project.settings.anthropic_api_key:
        console.print("[yellow]No API key set; vlogkit score is a no-op. Set VLOGKIT_ANTHROPIC_API_KEY.[/]")
        return 0

    clips = project.scan_clips()
    if not clips:
        console.print("[red]No video clips found.[/]")
        return 0

    backend = ClaudeBackend(project.settings)
    backend.model = project.settings.score_model
    weights = load_project_weights(project.root)

    # Pre-count total scenes for progress reporting
    total_scenes = 0
    for clip in clips:
        analysis = project.load_analysis(clip)
        if analysis is not None:
            total_scenes += len(analysis.scenes)

    scored_total = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scoring scenes...", total=None)

        for clip in clips:
            analysis = project.load_analysis(clip)
            if analysis is None:
                console.print(f"[yellow]Skipping {clip.name} — no analysis cached. Run `vlogkit analyze` first.[/]")
                continue

            scene_count = len(analysis.scenes)
            if scene_count == 0:
                console.print(f"[yellow]Skipping {clip.name} — no scenes detected.[/]")
                continue

            mutated = False
            for idx, scene in enumerate(analysis.scenes):
                if scene.murch is not None and not force:
                    continue
                progress.update(task, description=f"Scoring {clip.name} scene {idx + 1}/{scene_count}...")
                transcript_text = _transcript_for_scene(analysis, scene.start, scene.end)
                try:
                    score = score_scene(
                        scene=scene,
                        scene_index=idx,
                        scenes=analysis.scenes,
                        clip_filename=clip.name,
                        transcript_text=transcript_text,
                        backend=backend,
                        weights=weights,
                    )
                except ScoringError as e:
                    console.print(f"[yellow]Scoring failed for {clip.name} scene {idx}: {e}[/]")
                    continue

                scene.murch = score
                mutated = True
                scored_total += 1
                if progress_callback is not None:
                    progress_callback(
                        "scene_scored",
                        current_clip=clip.name,
                        current_scene_index=idx,
                        scored=scored_total,
                        total_scenes=total_scenes,
                    )

            if mutated:
                project.save_analysis(analysis)
                if progress_callback is not None:
                    composites = [
                        s.murch.composite for s in analysis.scenes if s.murch is not None
                    ]
                    avg = sum(composites) / len(composites) if composites else 0.0
                    progress_callback(
                        "clip_done",
                        clip_filename=clip.name,
                        average_composite=avg,
                    )

    console.print(f"[green]Scored {scored_total} scene(s).[/]")
    return scored_total
```

The change adds:
1. `progress_callback` parameter with default `None`
2. Pre-counting `total_scenes` before the loop
3. Calling the callback after each scene is scored (`scene_scored`)
4. Calling the callback after each clip's scenes finish (`clip_done`) with average_composite

- [ ] **Step 4: Run test to verify it passes**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_score.py -v
```

Expected: all score tests pass (existing 19 + new 1 = 20).

- [ ] **Step 5: Write failing test for `run_score_job`**

Create `tests/server/test_score_job.py`:

```python
"""Tests for the async score job + WS event emission."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def _make_project_with_scenes(tmp_path: Path):
    """Build a minimal Project with one cached clip having two scenes."""
    from vlogkit.config import Settings
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
    from vlogkit.project import Project

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path=clip, duration=10.0, resolution=(1, 1), fps=30.0, file_size=4
        ),
        scenes=[SceneSegment(start=0, end=5), SceneSegment(start=5, end=10)],
        file_hash="x",
    )
    project = Project(tmp_path, settings=Settings(anthropic_api_key="test-key", score_model="fake"))
    return project, clip, analysis


def test_run_score_job_publishes_started_progress_and_complete(tmp_path, monkeypatch):
    """The job must publish score.started, then score.progress per scene, then score.complete."""
    from vlogkit.models import MurchScore
    from vlogkit.project import Project
    from vlogkit.score import scorer as scorer_module
    from vlogkit.server import jobs as jobs_module
    from vlogkit.server.schemas import ScoreClipDone, ScoreComplete, ScoreProgress, ScoreStarted

    project, clip, analysis = _make_project_with_scenes(tmp_path)
    monkeypatch.setattr(Project, "scan_clips", lambda self: [clip])
    monkeypatch.setattr(Project, "load_analysis", lambda self, c: analysis)
    monkeypatch.setattr(Project, "save_analysis", lambda self, a: None)
    monkeypatch.setattr(scorer_module, "score_scene", lambda **kw: MurchScore(
        scene_type="narrative", aesthetic=50, credibility=50, impact=50,
        memorability=50, fun=50, composite=50.0,
    ))

    class FakeBackend:
        model = "fake"
        def complete(self, p, system=""):
            return ""
    monkeypatch.setattr("vlogkit.score.scorer.ClaudeBackend", lambda s: FakeBackend())

    published: list = []

    class FakeBroker:
        async def publish(self, project_id: str, event):
            published.append((project_id, event))

    asyncio.run(jobs_module.run_score_job(
        broker=FakeBroker(), project_id="p", project=project, job_id="j", force=False,
    ))

    types = [type(evt).__name__ for _pid, evt in published]
    assert types[0] == "ScoreStarted"
    assert "ScoreProgress" in types
    assert "ScoreClipDone" in types
    assert types[-1] == "ScoreComplete"

    # ScoreProgress should appear once per scene (2 here)
    assert sum(1 for t in types if t == "ScoreProgress") == 2


def test_run_score_job_publishes_failed_on_exception(tmp_path, monkeypatch):
    from vlogkit.project import Project
    from vlogkit.score import scorer as scorer_module
    from vlogkit.server import jobs as jobs_module
    from vlogkit.server.schemas import ScoreFailed

    project, clip, _analysis = _make_project_with_scenes(tmp_path)
    monkeypatch.setattr(Project, "scan_clips", lambda self: [clip])

    def boom(*a, **k):
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(scorer_module, "run_scoring", boom)

    published: list = []

    class FakeBroker:
        async def publish(self, project_id, event):
            published.append((project_id, event))

    asyncio.run(jobs_module.run_score_job(
        broker=FakeBroker(), project_id="p", project=project, job_id="j", force=False,
    ))

    types = [type(evt).__name__ for _pid, evt in published]
    assert "ScoreFailed" in types
    failed = [evt for _pid, evt in published if isinstance(evt, ScoreFailed)][0]
    assert "simulated failure" in failed.error
```

- [ ] **Step 6: Run to confirm fail**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/test_score_job.py -v
```

Expected: FAIL with `AttributeError: module 'vlogkit.server.jobs' has no attribute 'run_score_job'`.

- [ ] **Step 7: Add `run_score_job` to `src/vlogkit/server/jobs.py`**

Append to the end of `src/vlogkit/server/jobs.py`:

```python
async def run_score_job(
    broker: WsBroker,
    project_id: str,
    project: Project,
    job_id: str,
    force: bool = False,
) -> None:
    """Run scoring on all clips, emitting WS events as it goes."""
    from vlogkit.score import scorer as scorer_module
    from vlogkit.server.schemas import (
        ScoreClipDone,
        ScoreComplete,
        ScoreFailed,
        ScoreProgress,
        ScoreStarted,
    )

    # Pre-count total scenes for the started event
    clips = project.scan_clips()
    total_scenes = 0
    for clip in clips:
        analysis = project.load_analysis(clip)
        if analysis is not None:
            total_scenes += len(analysis.scenes)

    await broker.publish(
        project_id,
        ScoreStarted(job_id=job_id, total_scenes=total_scenes),
    )

    loop = asyncio.get_running_loop()

    def progress_callback(event_type: str, **kwargs) -> None:
        """Bridge sync run_scoring to the async broker via the loop."""
        if event_type == "scene_scored":
            evt = ScoreProgress(
                job_id=job_id,
                scored=kwargs["scored"],
                total_scenes=kwargs["total_scenes"],
                current_clip=kwargs["current_clip"],
                current_scene_index=kwargs["current_scene_index"],
            )
        elif event_type == "clip_done":
            evt = ScoreClipDone(
                job_id=job_id,
                clip_filename=kwargs["clip_filename"],
                average_composite=kwargs["average_composite"],
            )
        else:
            return
        # Schedule the publish on the event loop from this sync callback
        asyncio.run_coroutine_threadsafe(broker.publish(project_id, evt), loop)

    try:
        # run_scoring is sync; run it in a thread to avoid blocking the loop
        scored = await asyncio.to_thread(
            scorer_module.run_scoring,
            project,
            force,
            progress_callback,
        )
        await broker.publish(
            project_id,
            ScoreComplete(job_id=job_id, total_scored=scored),
        )
    except Exception as e:
        await broker.publish(
            project_id,
            ScoreFailed(job_id=job_id, error=str(e)),
        )
```

Note: the existing `run_analyze_job` in jobs.py already imports `asyncio`. If your jobs.py has a top-level `import asyncio`, you don't need to add it again.

- [ ] **Step 8: Run job tests**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/test_score_job.py -v
```

Expected: 2 passed.

- [ ] **Step 9: Convert the score route to async response**

Replace the contents of `src/vlogkit/server/routes/score.py` with:

```python
"""POST /projects/{id}/score — async; runs Murch scoring in a background thread."""

from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, Depends, status

from vlogkit.project import Project
from vlogkit.server import jobs as jobs_module
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_broker, get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail
from vlogkit.server.ws import WsBroker


def _run_job_in_thread(
    broker: WsBroker,
    project_id: str,
    project: Project,
    job_id: str,
    force: bool,
) -> threading.Thread:
    """Spawn a thread running the coroutine on its own fresh event loop.

    Same pattern as analyze.py — TestClient-friendly and safe under uvicorn.
    """

    def target() -> None:
        asyncio.run(
            jobs_module.run_score_job(broker, project_id, project, job_id, force)
        )

    t = threading.Thread(target=target, daemon=True, name=f"score-{job_id[:8]}")
    t.start()
    return t


def create_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/projects/{project_id}/score",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_token)],
        responses={404: {"model": ErrorDetail}},
    )
    async def start_score(
        project_id: str,
        force: bool = False,
        registry: ProjectRegistry = Depends(get_registry),
        broker: WsBroker = Depends(get_broker),
    ) -> dict[str, str]:
        project = load_project(registry, project_id)
        job_id = jobs_module.new_job_id()
        _run_job_in_thread(broker, project_id, project, job_id, force)
        return {"job_id": job_id}

    return router
```

- [ ] **Step 10: Update `tests/server/test_score_route.py` for new shape**

The existing tests assume `200` + `{"scored": N}` (synchronous). Replace `tests/server/test_score_route.py` with the async version:

```python
"""Tests for POST /projects/{id}/score (async + threaded)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _make_client(tmp_path: Path) -> tuple[TestClient, str]:
    """Build a test client for the desktop server with a one-project registry."""
    from vlogkit.server.app import create_desktop_app

    project_root = tmp_path / "p"
    project_root.mkdir()
    registry = tmp_path / "registry.json"
    # Match the ProjectRegistry expected format
    registry.write_text(json.dumps([
        {"id": "p", "path": str(project_root), "name": "p", "last_opened": 0}
    ]))

    token = "test-token"
    app = create_desktop_app(registry_path=registry, token=token)
    return TestClient(app), token


def test_score_route_returns_job_id_with_202(tmp_path, monkeypatch):
    """Endpoint should be async — return 202 with {job_id} immediately."""
    monkeypatch.setattr(
        "vlogkit.server.jobs.run_score_job",
        lambda **kw: None,  # job's a no-op for this test
    )

    client, token = _make_client(tmp_path)
    resp = client.post(
        "/projects/p/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "job_id" in body
    assert isinstance(body["job_id"], str) and len(body["job_id"]) > 0


def test_score_route_force_query_param_propagates(tmp_path, monkeypatch):
    """?force=true must reach run_score_job."""
    captured: dict[str, object] = {}

    async def fake_run_score_job(broker, project_id, project, job_id, force=False):
        captured["force"] = force

    monkeypatch.setattr("vlogkit.server.jobs.run_score_job", fake_run_score_job)

    client, token = _make_client(tmp_path)
    resp = client.post(
        "/projects/p/score?force=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 202

    # Give the spawned thread a moment to start the coroutine
    import time
    for _ in range(20):
        if "force" in captured:
            break
        time.sleep(0.05)
    assert captured.get("force") is True


def test_score_route_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setattr("vlogkit.server.jobs.run_score_job", lambda **kw: None)
    client, _token = _make_client(tmp_path)
    resp = client.post("/projects/p/score")
    assert resp.status_code in (401, 403)


def test_score_route_unknown_project_returns_404(tmp_path, monkeypatch):
    client, token = _make_client(tmp_path)
    resp = client.post(
        "/projects/nonexistent/score",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 11: Run the full server test directory**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/test_score_route.py tests/server/test_score_job.py tests/server/test_event_models.py tests/test_score.py -v
```

Expected: all pass.

- [ ] **Step 12: Commit**

```bash
git add src/vlogkit/score/scorer.py src/vlogkit/server/jobs.py src/vlogkit/server/routes/score.py tests/server/test_score_job.py tests/server/test_score_route.py tests/test_score.py
git commit -m "$(cat <<'EOF'
feat(server): convert score endpoint to async + emit score.* events

run_scoring gains an optional progress_callback parameter, called
after each scene scored ("scene_scored") and after each clip's last
scene ("clip_done", with average_composite). The new run_score_job in
jobs.py wires that callback to the WS broker, publishing ScoreStarted
on entry, ScoreProgress per scene, ScoreClipDone per clip, and
ScoreComplete on success (or ScoreFailed on exception).

The route now returns 202 with {job_id} and runs the scorer in a
background thread, mirroring the analyze pattern. Per-test verification
of the existing sync return shape is replaced.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Wire `storyboard.agent_*` events into `build_storyboard`

**Files:**
- Modify: `src/vlogkit/storyboard/builder.py` — accept optional `event_callback`
- Modify: `tests/test_storyboard_builder.py` — add tests for agent events

- [ ] **Step 1: Write failing test for event callback**

Append to `tests/test_storyboard_builder.py`:

```python
def test_build_storyboard_emits_agent_events_through_callback(tmp_path, monkeypatch):
    """When event_callback is provided, build_storyboard reports each stage's start/complete."""
    from vlogkit.config import Settings
    from vlogkit.models import Storyboard, StoryboardSection, StoryboardSegment
    from vlogkit.storyboard import builder as builder_module
    from vlogkit.storyboard.agents.director import DirectorPlan
    from vlogkit.storyboard.agents.editor import EditorAssignments

    monkeypatch.setattr(
        "vlogkit.storyboard.builder.director.run",
        lambda **kw: DirectorPlan(title="t", sections=[]),
    )
    monkeypatch.setattr(
        "vlogkit.storyboard.builder.editor.run",
        lambda **kw: EditorAssignments(assignments=[]),
    )
    monkeypatch.setattr(
        "vlogkit.storyboard.builder.polisher.run",
        lambda **kw: Storyboard(
            title="Final",
            sections=[StoryboardSection(title="S", segments=[])],
            total_duration=0.0,
            llm_rationale="ok",
        ),
    )

    events: list[tuple[str, str, str]] = []

    def callback(event_type: str, stage: str, summary_or_reason: str = ""):
        events.append((event_type, stage, summary_or_reason))

    builder_module.build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key="test-key"),
        strategy="energy-arc",
        context="trip",
        event_callback=callback,
    )

    # 6 events: started + complete for each of 3 stages
    assert [e[0] for e in events] == [
        "agent_started", "agent_complete",
        "agent_started", "agent_complete",
        "agent_started", "agent_complete",
    ]
    assert [e[1] for e in events] == [
        "director", "director",
        "editor", "editor",
        "polisher", "polisher",
    ]


def test_build_storyboard_emits_agent_failed_on_director_error(tmp_path, monkeypatch):
    from vlogkit.config import Settings
    from vlogkit.storyboard import builder as builder_module
    from vlogkit.storyboard.agents.base import AgentError

    monkeypatch.setattr(
        "vlogkit.storyboard.builder.director.run",
        lambda **kw: (_ for _ in ()).throw(AgentError(stage="director", reason="boom")),
    )

    events: list[tuple[str, str, str]] = []

    def callback(event_type: str, stage: str, summary_or_reason: str = ""):
        events.append((event_type, stage, summary_or_reason))

    builder_module.build_storyboard(
        analyses=[_make_analysis()],
        project_root=tmp_path,
        settings=Settings(anthropic_api_key="test-key"),
        strategy="energy-arc",
        context="trip",
        event_callback=callback,
    )

    # Should see director_started, then director_failed (no editor or polisher)
    types_and_stages = [(e[0], e[1]) for e in events]
    assert ("agent_started", "director") in types_and_stages
    assert ("agent_failed", "director") in types_and_stages
    assert all(e[1] != "editor" for e in events)
    assert all(e[1] != "polisher" for e in events)
```

- [ ] **Step 2: Run to confirm fail**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_builder.py -v
```

Expected: 2 new tests fail because `build_storyboard` doesn't accept `event_callback`.

- [ ] **Step 3: Modify `build_storyboard` to support `event_callback`**

Replace the contents of `src/vlogkit/storyboard/builder.py` with:

```python
"""Build a storyboard via the Director → Editor → Polisher multi-agent pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from rich.console import Console

from ..config import Settings
from ..llm.claude import ClaudeBackend
from ..models import ClipAnalysis, Storyboard
from .agents import director, editor, polisher
from .agents.base import AgentError
from .strategies import chronological_fallback

console = Console()

EventCallback = Callable[..., None]


def build_storyboard(
    analyses: list[ClipAnalysis],
    project_root: Path,
    settings: Settings,
    strategy: str = "energy-arc",
    context: str = "a recent trip",
    event_callback: EventCallback | None = None,
) -> Storyboard:
    """Generate a storyboard via the multi-agent pipeline.

    No API key → chronological fallback (no LLM, no events).
    Any agent failure → chronological fallback with a warning naming the stage.

    event_callback (when provided) is invoked with:
      - ("agent_started", stage)
      - ("agent_complete", stage, summary)
      - ("agent_failed", stage, reason)
    """
    if not settings.anthropic_api_key:
        console.print("[yellow]No API key found. Using chronological fallback.[/]")
        return chronological_fallback(analyses)

    backend = ClaudeBackend(settings)
    backend.model = settings.storyboard_model

    def emit(event_type: str, stage: str, summary_or_reason: str = "") -> None:
        if event_callback is not None:
            event_callback(event_type, stage, summary_or_reason)

    try:
        console.print("[cyan]Director: planning narrative arc...[/]")
        emit("agent_started", "director")
        plan = director.run(
            analyses=analyses, strategy=strategy, context=context, backend=backend,
        )
        emit("agent_complete", "director", f"Planned {len(plan.sections)} sections")

        console.print("[cyan]Editor: selecting scenes...[/]")
        emit("agent_started", "editor")
        assignments = editor.run(plan=plan, analyses=analyses, backend=backend)
        n_picks = sum(len(a.picks) for a in assignments.assignments)
        emit("agent_complete", "editor", f"Picked {n_picks} segments")

        console.print("[cyan]Polisher: finalizing transitions and labels...[/]")
        emit("agent_started", "polisher")
        storyboard = polisher.run(
            plan=plan, assignments=assignments, analyses=analyses,
            project_root=project_root, backend=backend,
        )
        emit("agent_complete", "polisher", "Storyboard ready")

        console.print(
            f"[green]Storyboard created: {len(storyboard.sections)} section(s).[/]"
        )
        return storyboard

    except AgentError as e:
        emit("agent_failed", e.stage, e.reason)
        console.print(
            f"[yellow]Multi-agent flow failed at stage '{e.stage}': {e.reason}. "
            f"Falling back to chronological order.[/]"
        )
        return chronological_fallback(analyses)
```

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/test_storyboard_builder.py tests/test_storyboard_agents.py -v
```

Expected: all pass (5 prior builder + 2 new = 7, plus 15 agent tests).

- [ ] **Step 5: Update the storyboard regenerate job to bridge the callback to the broker**

Find the existing storyboard regenerate job in `src/vlogkit/server/jobs.py`. (If it's named `run_storyboard_regen_job` or similar, locate it via `grep -n "storyboard" src/vlogkit/server/jobs.py`.)

Inside that function, where it currently calls `build_storyboard(...)`, replace that call with one that bridges the callback to the broker:

```python
# Inside run_storyboard_regen_job (or whatever the existing function is named):

loop = asyncio.get_running_loop()

def event_callback(event_type: str, stage: str, summary_or_reason: str = ""):
    from vlogkit.server.schemas import (
        StoryboardAgentComplete, StoryboardAgentFailed, StoryboardAgentStarted,
    )
    if event_type == "agent_started":
        evt = StoryboardAgentStarted(job_id=job_id, stage=stage)
    elif event_type == "agent_complete":
        evt = StoryboardAgentComplete(job_id=job_id, stage=stage, summary=summary_or_reason)
    elif event_type == "agent_failed":
        evt = StoryboardAgentFailed(job_id=job_id, stage=stage, reason=summary_or_reason)
    else:
        return
    asyncio.run_coroutine_threadsafe(broker.publish(project_id, evt), loop)

storyboard = await asyncio.to_thread(
    build_storyboard,
    analyses, project.root, project.settings,
    strategy, context,
    event_callback,
)
```

The exact integration depends on the existing function's signature — find the call site to `build_storyboard` and adapt.

If the existing storyboard regen job doesn't yet exist (just calls `build_storyboard` synchronously inside the route handler), wrap it in `asyncio.to_thread` and add the callback as shown above.

- [ ] **Step 6: Commit**

```bash
git add src/vlogkit/storyboard/builder.py src/vlogkit/server/jobs.py tests/test_storyboard_builder.py
git commit -m "$(cat <<'EOF'
feat(server): emit storyboard.agent_* events from build_storyboard

build_storyboard accepts an optional event_callback that receives
(event_type, stage, summary_or_reason) for each Director/Editor/Polisher
stage transition. The storyboard regenerate job bridges the callback
to the WS broker, publishing StoryboardAgentStarted on each stage entry,
StoryboardAgentComplete with a short summary on success, and
StoryboardAgentFailed with the AgentError reason on failure.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add typed `ClipAnalysisSummary` schema + clips route adapter

**Files:**
- Modify: `src/vlogkit/server/schemas.py` — add `ClipScene`, `ClipMurchScore`, `ClipAnalysisSummary`; modify `ClipSummary.analysis` to typed
- Modify: `src/vlogkit/server/routes/clips.py` — adapt internal `ClipAnalysis` to the new shape
- Create: `tests/server/test_clips_route_analysis_shape.py`

- [ ] **Step 1: Write failing test**

Create `tests/server/test_clips_route_analysis_shape.py`:

```python
"""Verifies GET /projects/{id}/clips returns typed analysis.scenes[].murch."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _make_client_with_analyzed_project(tmp_path: Path):
    """Build a desktop server client; project has one clip with analysis cached, including a Murch score."""
    from vlogkit.config import Settings
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
    from vlogkit.project import Project
    from vlogkit.server.app import create_desktop_app

    project_root = tmp_path / "p"
    project_root.mkdir()
    clip_file = project_root / "clip.mp4"
    clip_file.write_bytes(b"fake")

    project = Project(project_root, settings=Settings(anthropic_api_key="x"))
    analysis = ClipAnalysis(
        metadata=ClipMetadata(
            filename="clip.mp4", path=clip_file, duration=10.0,
            resolution=(1, 1), fps=30.0, file_size=4,
        ),
        scenes=[
            SceneSegment(
                start=0, end=5, description="opening shot", tags=["sky"],
                murch=MurchScore(
                    scene_type="hook", aesthetic=80, credibility=70, impact=90,
                    memorability=85, fun=60, composite=82.0, rationale="strong",
                ),
            ),
            SceneSegment(start=5, end=10),  # unscored
        ],
        file_hash="x",
    )
    project.save_analysis(analysis)

    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps([
        {"id": "p", "path": str(project_root), "name": "p", "last_opened": 0}
    ]))

    token = "test-token"
    app = create_desktop_app(registry_path=registry, token=token)
    return TestClient(app), token


def test_clips_route_returns_typed_scenes_with_murch(tmp_path):
    client, token = _make_client_with_analyzed_project(tmp_path)
    resp = client.get(
        "/projects/p/clips",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    clips = resp.json()
    assert len(clips) == 1
    clip = clips[0]
    assert clip["filename"] == "clip.mp4"
    assert clip["analysis"] is not None
    assert "scenes" in clip["analysis"]
    scenes = clip["analysis"]["scenes"]
    assert len(scenes) == 2

    # First scene has a murch score
    assert scenes[0]["murch"] is not None
    assert scenes[0]["murch"]["scene_type"] == "hook"
    assert scenes[0]["murch"]["composite"] == 82.0
    assert scenes[0]["description"] == "opening shot"
    assert scenes[0]["tags"] == ["sky"]

    # Second scene has no murch
    assert scenes[1]["murch"] is None
```

- [ ] **Step 2: Run to confirm fail**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/test_clips_route_analysis_shape.py -v
```

Expected: FAIL — current shape has `analysis` as opaque dict.

- [ ] **Step 3: Add the new schemas to `src/vlogkit/server/schemas.py`**

Append (or insert near the existing `ClipSummary`) in `src/vlogkit/server/schemas.py`:

```python
# ---- Typed analysis shape exposed to the renderer (new) ----

class ClipMurchScore(BaseModel):
    scene_type: Literal["hook", "narrative", "aesthetic", "commercial"]
    aesthetic: float
    credibility: float
    impact: float
    memorability: float
    fun: float
    composite: float
    rationale: str = ""


class ClipScene(BaseModel):
    start: float
    end: float
    description: str = ""
    tags: list[str] = []
    keyframe_path: str | None = None
    murch: ClipMurchScore | None = None


class ClipAnalysisSummary(BaseModel):
    scenes: list[ClipScene] = []
    summary: str = ""
```

Then locate the existing `ClipSummary` class. It currently has `analysis: dict | None = None` (or similar). Change the type to:

```python
class ClipSummary(BaseModel):
    # ...existing fields...
    analysis: ClipAnalysisSummary | None = None    # CHANGED
```

- [ ] **Step 4: Add adapter in `src/vlogkit/server/routes/clips.py`**

Find the existing `list_clips` handler in `src/vlogkit/server/routes/clips.py`. It iterates over project clips and constructs `ClipSummary` objects. Where it currently sets `analysis=...` (likely from `analysis.model_dump()` or `dict(analysis)`), replace with the conversion through the new typed schema.

Add a helper (near the top of `clips.py` or in a private function):

```python
def _to_clip_analysis_summary(analysis):
    """Convert internal ClipAnalysis → ClipAnalysisSummary (the API-facing shape)."""
    from vlogkit.server.schemas import ClipAnalysisSummary, ClipMurchScore, ClipScene

    scenes = []
    for s in analysis.scenes:
        murch = None
        if s.murch is not None:
            murch = ClipMurchScore(
                scene_type=s.murch.scene_type,
                aesthetic=s.murch.aesthetic,
                credibility=s.murch.credibility,
                impact=s.murch.impact,
                memorability=s.murch.memorability,
                fun=s.murch.fun,
                composite=s.murch.composite,
                rationale=s.murch.rationale,
            )
        scenes.append(ClipScene(
            start=s.start, end=s.end,
            description=s.description, tags=list(s.tags),
            keyframe_path=str(s.keyframe_path) if s.keyframe_path else None,
            murch=murch,
        ))
    return ClipAnalysisSummary(scenes=scenes, summary=analysis.summary or "")
```

Then in the handler where `ClipSummary` is constructed, pass `analysis=_to_clip_analysis_summary(loaded_analysis) if loaded_analysis else None`. The exact structure of the existing handler depends on how clips are listed today — read `routes/clips.py` and adapt.

- [ ] **Step 5: Run the test to verify it passes**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/test_clips_route_analysis_shape.py -v
```

Expected: PASS.

- [ ] **Step 6: Run full server test suite to check for regressions**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/ -v 2>&1 | tail -25
```

Expected: new tests pass; pre-existing pytest-asyncio + openapi-snapshot failures unchanged. If the openapi snapshot test now fails for NEW reasons (typed analysis shape), that's expected — it'll be regenerated in Task 5.

- [ ] **Step 7: Commit**

```bash
git add src/vlogkit/server/schemas.py src/vlogkit/server/routes/clips.py tests/server/test_clips_route_analysis_shape.py
git commit -m "$(cat <<'EOF'
feat(server): typed scenes/murch in ClipSummary.analysis

Adds ClipScene, ClipMurchScore, ClipAnalysisSummary models so the
renderer can read scores without parsing freeform JSON. The clips
route adapter converts the internal ClipAnalysis into the typed
API shape, exposing scenes[].murch as a typed nullable field.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Regenerate `api-types.ts`

**Files:**
- Modify: `desktop/web/src/lib/api-types.ts`
- Modify: `tests/server/snapshots/openapi.json` (regenerate)

- [ ] **Step 1: Regenerate the OpenAPI snapshot**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
VLOGKIT_UPDATE_SNAPSHOTS=1 PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/test_openapi_snapshot.py
```

This rewrites `tests/server/snapshots/openapi.json` to include the new event models + typed analysis shape.

- [ ] **Step 2: Verify the snapshot test now passes**

```bash
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest tests/server/test_openapi_snapshot.py -v
```

Expected: PASS.

- [ ] **Step 3: Generate api-types.ts from the snapshot**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -c "
from vlogkit.server.app import create_desktop_app
import json, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as t:
    reg = Path(t) / 'r.json'; reg.write_text('[]')
    app = create_desktop_app(registry_path=reg, token='x')
    Path('/tmp/openapi.json').write_text(json.dumps(app.openapi()))
print('OpenAPI schema written to /tmp/openapi.json')
"
npx --prefix desktop/web openapi-typescript /tmp/openapi.json -o desktop/web/src/lib/api-types.ts
```

- [ ] **Step 4: Verify the renderer typechecks**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
npx --prefix desktop/web tsc --noEmit
```

Expected: clean (zero errors). If `api.ts` references `ClipSummary["analysis"]` anywhere that breaks because the shape changed from `unknown` to `ClipAnalysisSummary | null`, fix the usage.

- [ ] **Step 5: Commit**

```bash
git add desktop/web/src/lib/api-types.ts tests/server/snapshots/openapi.json
git commit -m "$(cat <<'EOF'
chore(types): regenerate api-types.ts and openapi snapshot

Picks up the new score.* and storyboard.agent_* event models, the
score endpoint's async response shape (202 + {job_id}), and the
typed ClipScene/ClipMurchScore/ClipAnalysisSummary structure exposed
via ClipSummary.analysis.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add `api.score()` method + extend renderer event types

**Files:**
- Modify: `desktop/web/src/lib/api.ts`
- Modify: `desktop/web/src/lib/events.ts`

- [ ] **Step 1: Add `score()` method to `desktop/web/src/lib/api.ts`**

Find the existing `api` object in `desktop/web/src/lib/api.ts` (line ~62). Add a new method after `regenerateStoryboard`:

```typescript
  score: (projectId: string, force = false) =>
    request<{ job_id: string }>(
      `/projects/${projectId}/score${force ? "?force=true" : ""}`,
      { method: "POST" },
    ),
```

- [ ] **Step 2: Extend event types in `desktop/web/src/lib/events.ts`**

Append to `desktop/web/src/lib/events.ts`:

```typescript

// ---- Score events (new) ----

export type ScoreStarted = {
  type: "score.started";
  job_id: string;
  total_scenes: number;
};
export type ScoreProgress = {
  type: "score.progress";
  job_id: string;
  scored: number;
  total_scenes: number;
  current_clip: string;
  current_scene_index: number;
};
export type ScoreClipDone = {
  type: "score.clip_done";
  job_id: string;
  clip_filename: string;
  average_composite: number;
};
export type ScoreComplete = {
  type: "score.complete";
  job_id: string;
  total_scored: number;
};
export type ScoreFailed = {
  type: "score.failed";
  job_id: string;
  error: string;
};

export type ScoreEvent =
  | ScoreStarted
  | ScoreProgress
  | ScoreClipDone
  | ScoreComplete
  | ScoreFailed;

// ---- Storyboard agent stage events (new) ----

export type StoryboardAgentStage = "director" | "editor" | "polisher";

export type StoryboardAgentStarted = {
  type: "storyboard.agent_started";
  job_id: string;
  stage: StoryboardAgentStage;
};
export type StoryboardAgentComplete = {
  type: "storyboard.agent_complete";
  job_id: string;
  stage: StoryboardAgentStage;
  summary: string;
};
export type StoryboardAgentFailed = {
  type: "storyboard.agent_failed";
  job_id: string;
  stage: StoryboardAgentStage;
  reason: string;
};

export type StoryboardAgentEvent =
  | StoryboardAgentStarted
  | StoryboardAgentComplete
  | StoryboardAgentFailed;
```

Then update the existing `BoardEvent` union (at the bottom of the file) to include the new types:

```typescript
export type BoardEvent =
  | AnalyzeEvent
  | ScoreEvent                    // NEW
  | StoryboardRegenStarted
  | StoryboardRegenToken
  | StoryboardRegenComplete
  | StoryboardRegenFailed
  | StoryboardAgentEvent;         // NEW
```

- [ ] **Step 3: Typecheck**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
npx --prefix desktop/web tsc --noEmit
```

Expected: clean.

- [ ] **Step 4: Lint**

```bash
npm --prefix desktop/web run lint 2>&1 | tail -5
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add desktop/web/src/lib/api.ts desktop/web/src/lib/events.ts
git commit -m "$(cat <<'EOF'
feat(renderer): add api.score() + score and agent event types

api.score(projectId, force?) hits the new async POST /score and
returns the job_id. Event union extended with ScoreEvent and
StoryboardAgentEvent so the reducer downstream can match on them.
Hand-typed to mirror the server-side schemas (WS messages don't
appear in OpenAPI).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Renderer primitives — CompositeChip, SceneTypeChip, DimensionBar

**Files:**
- Create: `desktop/web/src/components/clips/composite-chip.tsx`
- Create: `desktop/web/src/components/clips/scene-type-chip.tsx`
- Create: `desktop/web/src/components/clips/dimension-bar.tsx`

- [ ] **Step 1: Create `composite-chip.tsx`**

```tsx
"use client";

/**
 * Color-tiered composite score chip.
 *
 * Tiers (numeric thresholds, tunable):
 *   0-49  → red bg, dark red text     (weak)
 *   50-69 → amber bg, dark amber text (mid)
 *   70-84 → emerald bg, dark emerald  (good)
 *   85-100→ gold bg, dark gold + ★    (excellent)
 *
 * If `mixed` (only some scenes scored), append a "(scored/total)" suffix.
 */
export function CompositeChip({
  score,
  scoredCount,
  totalCount,
}: {
  score: number;
  scoredCount?: number;
  totalCount?: number;
}) {
  const tier = tierFor(score);
  const showStar = tier === "excellent";
  const suffix =
    scoredCount !== undefined &&
    totalCount !== undefined &&
    scoredCount < totalCount
      ? ` (${scoredCount}/${totalCount})`
      : "";

  return (
    <span
      className={`text-xs font-semibold px-2 py-0.5 rounded-full ${classesFor(tier)}`}
      title={`Composite score ${score.toFixed(0)}${suffix}`}
    >
      {showStar ? "★ " : ""}
      {Math.round(score)}
      {suffix}
    </span>
  );
}

type Tier = "weak" | "mid" | "good" | "excellent";

function tierFor(score: number): Tier {
  if (score >= 85) return "excellent";
  if (score >= 70) return "good";
  if (score >= 50) return "mid";
  return "weak";
}

function classesFor(tier: Tier): string {
  switch (tier) {
    case "excellent": return "bg-yellow-100 text-yellow-900";
    case "good":      return "bg-emerald-100 text-emerald-900";
    case "mid":       return "bg-amber-100 text-amber-900";
    case "weak":      return "bg-red-100 text-red-900";
  }
}
```

- [ ] **Step 2: Create `scene-type-chip.tsx`**

```tsx
"use client";

import type { components } from "@/lib/api-types";

type SceneType = components["schemas"]["ClipMurchScore"]["scene_type"];

const STYLES: Record<SceneType, string> = {
  hook:       "bg-blue-100 text-blue-900",
  narrative:  "bg-amber-100 text-amber-900",
  aesthetic:  "bg-emerald-100 text-emerald-900",
  commercial: "bg-purple-100 text-purple-900",
};

export function SceneTypeChip({ type }: { type: SceneType }) {
  return (
    <span
      className={`text-[10px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded ${STYLES[type]}`}
    >
      {type}
    </span>
  );
}
```

- [ ] **Step 3: Create `dimension-bar.tsx`**

```tsx
"use client";

/**
 * Small inline horizontal bar (0-100 → width). Used for the per-scene
 * dimension visualization in scene rows and the inspector readout.
 */
export function DimensionBar({
  value,
  label,
  width = 32,
}: {
  value: number;
  label?: string;
  width?: number;
}) {
  const pct = Math.max(0, Math.min(100, value));
  const barWidth = (pct / 100) * width;
  return (
    <span
      className="inline-flex items-center gap-1"
      title={label ? `${label}: ${value.toFixed(0)}` : `${value.toFixed(0)}`}
    >
      <span
        className="inline-block h-2 bg-gray-200 rounded-sm"
        style={{ width: `${width}px` }}
      >
        <span
          className="inline-block h-2 bg-blue-500 rounded-sm"
          style={{ width: `${barWidth}px` }}
        />
      </span>
    </span>
  );
}
```

- [ ] **Step 4: Typecheck + lint**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
npx --prefix desktop/web tsc --noEmit && npm --prefix desktop/web run lint
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add desktop/web/src/components/clips/composite-chip.tsx desktop/web/src/components/clips/scene-type-chip.tsx desktop/web/src/components/clips/dimension-bar.tsx
git commit -m "$(cat <<'EOF'
feat(renderer): CompositeChip, SceneTypeChip, DimensionBar primitives

Three small reusable visual primitives. CompositeChip color-tiers a
0-100 score (weak/mid/good/excellent) with a star flourish on the
top tier and a "(scored/total)" suffix when only some scenes have a
murch. SceneTypeChip uses semantic colors per Murch scene type.
DimensionBar is a small horizontal bar for per-dimension readouts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: SceneRow + ScoreButton + Clip card expand

**Files:**
- Create: `desktop/web/src/components/clips/scene-row.tsx`
- Create: `desktop/web/src/components/clips/score-button.tsx`
- Modify: `desktop/web/src/components/clips/clip-card.tsx`
- Modify: `desktop/web/src/components/clips/clip-list.tsx`

- [ ] **Step 1: Create `scene-row.tsx`**

```tsx
"use client";

import type { components } from "@/lib/api-types";
import { CompositeChip } from "./composite-chip";
import { DimensionBar } from "./dimension-bar";
import { SceneTypeChip } from "./scene-type-chip";

type ClipScene = components["schemas"]["ClipScene"];

function formatTime(s: number): string {
  if (s < 60) return `${s.toFixed(0)}s`;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export function SceneRow({ scene }: { scene: ClipScene }) {
  if (!scene.murch) {
    return (
      <div className="grid grid-cols-[60px_1fr] gap-2 py-1 text-xs text-[var(--color-placeholder)]">
        <span>{formatTime(scene.start)}–{formatTime(scene.end)}</span>
        <span className="italic">unscored</span>
      </div>
    );
  }
  const m = scene.murch;
  return (
    <div className="grid grid-cols-[60px_80px_50px_1fr] gap-2 py-1 items-center text-xs">
      <span className="text-[var(--color-muted)]">
        {formatTime(scene.start)}–{formatTime(scene.end)}
      </span>
      <span><SceneTypeChip type={m.scene_type} /></span>
      <span><CompositeChip score={m.composite} /></span>
      <span className="flex items-center gap-1">
        <DimensionBar value={m.aesthetic} label="Aesthetic" />
        <DimensionBar value={m.credibility} label="Credibility" />
        <DimensionBar value={m.impact} label="Impact" />
        <DimensionBar value={m.memorability} label="Memorability" />
        <DimensionBar value={m.fun} label="Fun" />
      </span>
    </div>
  );
}
```

- [ ] **Step 2: Create `score-button.tsx` (controlled — receives status as props)**

The existing pattern in this codebase has parent components own the WS subscription and pass progress state down. We follow the same pattern: `ClipsTab` will route score events; `ScoreButton` is presentational with a click handler.

```tsx
"use client";

import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

export type ScoreState =
  | { status: "idle" }
  | { status: "running"; scored: number; total: number }
  | { status: "completed" }
  | { status: "failed"; error: string };

export function ScoreButton({
  projectId,
  state,
  onJobStarted,
  disabled = false,
}: {
  projectId: string;
  state: ScoreState;
  onJobStarted: (jobId: string) => void;
  disabled?: boolean;
}) {
  const mutation = useMutation({
    mutationFn: () => api.score(projectId),
    onSuccess: (resp) => onJobStarted(resp.job_id),
  });

  const label = (() => {
    if (mutation.isPending) return "Starting…";
    if (state.status === "running") {
      return `Scoring ${state.scored} of ${state.total}…`;
    }
    if (state.status === "completed") return "Scored";
    if (state.status === "failed") return "Score failed (retry)";
    return "Score scenes";
  })();

  return (
    <button
      onClick={() => mutation.mutate()}
      disabled={disabled || mutation.isPending || state.status === "running"}
      className="px-3 py-1.5 rounded-[4px] font-semibold text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60 text-sm transition"
      title={state.status === "failed" ? state.error : undefined}
    >
      {label}
    </button>
  );
}
```

- [ ] **Step 3: Modify `clip-card.tsx` to add chip + expand**

Read the existing `desktop/web/src/components/clips/clip-card.tsx`. Replace its contents with:

```tsx
"use client";

import { useState } from "react";
import type { ClipSummary } from "@/lib/api";
import type { AnalyzeProgress } from "@/lib/events";
import { CompositeChip } from "./composite-chip";
import { SceneRow } from "./scene-row";

export function ClipCard({
  clip,
  progress,
}: {
  clip: ClipSummary;
  progress?: AnalyzeProgress;
}) {
  const analyzed = clip.status === "analyzed";
  const scenes = clip.analysis?.scenes ?? [];
  const scoredScenes = scenes.filter((s) => s.murch !== null);
  const hasAnyScores = scoredScenes.length > 0;
  const avgComposite =
    hasAnyScores
      ? scoredScenes.reduce((sum, s) => sum + (s.murch?.composite ?? 0), 0) /
        scoredScenes.length
      : 0;
  const canExpand = scenes.length > 0;

  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="bg-white rounded-[12px] border border-[var(--color-border-whisper)] p-4"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div
        className={canExpand ? "flex items-center justify-between cursor-pointer" : "flex items-center justify-between"}
        onClick={canExpand ? () => setExpanded((x) => !x) : undefined}
      >
        <div className="flex items-center gap-2">
          {canExpand && (
            <span className="text-[var(--color-muted)] text-sm w-3">
              {expanded ? "▾" : "▸"}
            </span>
          )}
          <div className="font-semibold">{clip.filename}</div>
        </div>
        <div className="flex items-center gap-2">
          {hasAnyScores && (
            <CompositeChip
              score={avgComposite}
              scoredCount={scoredScenes.length}
              totalCount={scenes.length}
            />
          )}
          <StatusPill status={clip.status} />
        </div>
      </div>
      <div className="text-xs text-[var(--color-placeholder)] mt-1">
        {(clip.size / 1024 / 1024).toFixed(1)} MB
        {scenes.length > 0 && ` · ${scenes.length} scene${scenes.length === 1 ? "" : "s"}`}
      </div>

      {!analyzed && progress && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-xs text-[var(--color-muted)]">
            <span>{progress.stage}</span>
            <span>{Math.round(progress.pct * 100)}%</span>
          </div>
          <div className="h-1 bg-[var(--color-background-alt)] rounded-full mt-1 overflow-hidden">
            <div
              className="h-full bg-[var(--color-accent)] transition-[width]"
              style={{ width: `${progress.pct * 100}%` }}
            />
          </div>
        </div>
      )}

      {canExpand && expanded && (
        <div className="mt-3 border-t border-[var(--color-border-whisper)] pt-2">
          {scenes.length === 0 ? (
            <p className="text-xs text-[var(--color-placeholder)] italic">
              No scenes detected.
            </p>
          ) : !hasAnyScores ? (
            <p className="text-xs text-[var(--color-placeholder)] italic">
              No scores yet. Run "Score scenes" to grade.
            </p>
          ) : (
            <div className="grid gap-1">
              {scenes.map((s, i) => (
                <SceneRow key={i} scene={s} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: ClipSummary["status"] }) {
  const styles = {
    unanalyzed: "bg-[var(--color-background-alt)] text-[var(--color-muted)]",
    analyzed: "bg-[var(--color-badge-bg)] text-[var(--color-badge-text)]",
    failed: "bg-red-50 text-red-700",
  }[status];
  return (
    <span
      className={`text-xs font-semibold px-2 py-0.5 rounded-full ${styles}`}
    >
      {status}
    </span>
  );
}
```

- [ ] **Step 4: Add `<ScoreButton />` to `clip-list.tsx` (parent owns score state + WS subscription)**

The existing `ClipsTab` already calls `connectEventStream` and routes analyze events. Extend it to also route score events into a new local `scoreState`, and pass `scoreState` to a new `<ScoreButton />` next to the existing `<AnalyzeButton />`.

Replace the contents of `desktop/web/src/components/clips/clip-list.tsx` with:

```tsx
"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { connectEventStream } from "@/lib/ws";
import type { BoardEvent, AnalyzeProgress } from "@/lib/events";
import { ClipCard } from "./clip-card";
import { AnalyzeButton } from "./analyze-button";
import { ScoreButton, type ScoreState } from "./score-button";

export function ClipsTab({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.clips(projectId),
    queryFn: () => api.listClips(projectId),
  });
  const [progress, setProgress] = useState<Record<string, AnalyzeProgress>>({});
  const [scoreJobId, setScoreJobId] = useState<string | null>(null);
  const [scoreState, setScoreState] = useState<ScoreState>({ status: "idle" });

  useEffect(() => {
    const disconnect = connectEventStream(projectId, (evt: BoardEvent) => {
      // Existing analyze routing
      if (evt.type === "analyze.progress") {
        setProgress((p) => ({ ...p, [evt.clip_filename]: evt }));
      } else if (evt.type === "analyze.clip_done") {
        setProgress((p) => {
          const { [evt.clip_filename]: _, ...rest } = p;
          return rest;
        });
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      } else if (evt.type === "analyze.clip_failed") {
        setProgress((p) => {
          const { [evt.clip_filename]: _, ...rest } = p;
          return rest;
        });
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      } else if (evt.type === "analyze.complete") {
        setProgress({});
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      }

      // New: score event routing — only act on events for the active score job
      if ("job_id" in evt && scoreJobId && evt.job_id === scoreJobId) {
        if (evt.type === "score.started") {
          setScoreState({ status: "running", scored: 0, total: evt.total_scenes });
        } else if (evt.type === "score.progress") {
          setScoreState({
            status: "running",
            scored: evt.scored,
            total: evt.total_scenes,
          });
        } else if (evt.type === "score.clip_done") {
          // Refetch clips so the per-clip composite chip updates live
          qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
        } else if (evt.type === "score.complete") {
          setScoreState({ status: "completed" });
          setScoreJobId(null);
          qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
        } else if (evt.type === "score.failed") {
          setScoreState({ status: "failed", error: evt.error });
          setScoreJobId(null);
        }
      }
    });
    return disconnect;
  }, [projectId, qc, scoreJobId]);

  if (isLoading) return <p className="text-[var(--color-muted)]">Loading clips…</p>;
  if (error) return <p className="text-red-600">Error: {String(error)}</p>;
  if (!data || data.length === 0) {
    return (
      <p className="text-[var(--color-muted)] py-12 text-center">
        No clips in this folder.
      </p>
    );
  }

  // Score button is disabled until at least one clip is analyzed
  const anyAnalyzed = data.some((c) => c.status === "analyzed");

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-[var(--color-muted)]">{data.length} clips</p>
        <div className="flex items-center gap-2">
          <AnalyzeButton projectId={projectId} />
          <ScoreButton
            projectId={projectId}
            state={scoreState}
            disabled={!anyAnalyzed}
            onJobStarted={(jobId) => {
              setScoreJobId(jobId);
              setScoreState({ status: "running", scored: 0, total: 0 });
            }}
          />
        </div>
      </div>
      <div className="grid gap-3">
        {data.map((c) => (
          <ClipCard
            key={c.filename}
            clip={c}
            progress={progress[c.filename]}
          />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Typecheck + lint**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
npx --prefix desktop/web tsc --noEmit && npm --prefix desktop/web run lint
```

Expected: clean. If `useProjectEvents` doesn't exist or has a different signature, adapt accordingly — the score button needs to listen for events filtered by `job_id`.

- [ ] **Step 6: Commit**

```bash
git add desktop/web/src/components/clips/scene-row.tsx desktop/web/src/components/clips/score-button.tsx desktop/web/src/components/clips/clip-card.tsx desktop/web/src/components/clips/clip-list.tsx
git commit -m "$(cat <<'EOF'
feat(renderer): ScoreButton + clip card expand for scores

ScoreButton kicks off the async score job and updates its label
("Scoring N of M…") from score.progress events. On score.clip_done,
invalidates the clips query so the per-clip composite chip refetches
live as scoring rolls through. Clip cards show the average composite
chip in their header (with mixed-state suffix) and gain an inline
expand-to-see-scenes section using SceneRow.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: AgentProgressStepper + Board integration

**Files:**
- Create: `desktop/web/src/components/board/agent-progress-stepper.tsx`
- Modify: `desktop/web/src/components/board/board.tsx`
- Modify: `desktop/web/src/components/board/regenerate-button.tsx` (if needed to expose job_id)

- [ ] **Step 1: Create `agent-progress-stepper.tsx` (controlled — receives stages as a prop)**

Following the existing pattern (parent owns the WS subscription), the stepper is a presentational component. The parent `Board` owns the agent-stage state and passes it down.

```tsx
"use client";

import { useEffect } from "react";
import type { StoryboardAgentStage } from "@/lib/events";

export type StepStatus = "pending" | "active" | "done" | "failed";

export interface StepState {
  status: StepStatus;
  summary: string;
}

export type AgentSteps = Record<StoryboardAgentStage, StepState>;

export const INITIAL_AGENT_STEPS: AgentSteps = {
  director: { status: "pending", summary: "" },
  editor: { status: "pending", summary: "" },
  polisher: { status: "pending", summary: "" },
};

const STAGES: StoryboardAgentStage[] = ["director", "editor", "polisher"];
const STAGE_TITLES: Record<StoryboardAgentStage, string> = {
  director: "Director",
  editor: "Editor",
  polisher: "Polisher",
};

export function AgentProgressStepper({
  steps,
  onComplete,
}: {
  steps: AgentSteps;
  onComplete?: () => void;
}) {
  // Fire onComplete shortly after polisher reaches done
  useEffect(() => {
    if (steps.polisher.status === "done") {
      const t = setTimeout(() => onComplete?.(), 800);
      return () => clearTimeout(t);
    }
  }, [steps.polisher.status, onComplete]);

  const anyFailed = STAGES.some((s) => steps[s].status === "failed");

  return (
    <div className="bg-white border border-[var(--color-border-whisper)] rounded-lg p-4 flex items-center gap-0">
      {STAGES.map((stage, i) => (
        <span key={stage} className="flex items-center flex-1">
          <Step number={i + 1} title={STAGE_TITLES[stage]} state={steps[stage]} />
          {i < STAGES.length - 1 && (
            <span
              className={`flex-shrink-0 mx-2 h-0.5 w-8 ${
                steps[stage].status === "done" ? "bg-emerald-500" : "bg-gray-200"
              }`}
            />
          )}
        </span>
      ))}
      {anyFailed && (
        <p className="text-xs text-red-700 mt-2 ml-2 flex-1">
          Falling back to chronological order.
        </p>
      )}
    </div>
  );
}

function Step({
  number,
  title,
  state,
}: {
  number: number;
  title: string;
  state: StepState;
}) {
  const circleClass =
    state.status === "done"
      ? "bg-emerald-500 text-white"
      : state.status === "active"
      ? "bg-blue-500 text-white"
      : state.status === "failed"
      ? "bg-red-500 text-white"
      : "bg-gray-200 text-[var(--color-muted)]";

  const subtitle =
    state.status === "active"
      ? "running…"
      : state.status === "done"
      ? state.summary || "done"
      : state.status === "failed"
      ? state.summary
      : "pending";

  const subtitleClass =
    state.status === "active"
      ? "text-blue-700"
      : state.status === "failed"
      ? "text-red-700"
      : "text-[var(--color-muted)]";

  return (
    <span className="flex items-center gap-2">
      <span
        className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${circleClass}`}
      >
        {state.status === "done" ? "✓" : state.status === "failed" ? "✕" : number}
      </span>
      <span>
        <span className="block text-xs font-semibold">{title}</span>
        <span className={`block text-[10px] ${subtitleClass}`}>{subtitle}</span>
      </span>
    </span>
  );
}
```

- [ ] **Step 2: Mount `<AgentProgressStepper />` in `board.tsx`**

Read `desktop/web/src/components/board/board.tsx` first to understand the existing structure. Board already calls `connectEventStream` (line ~57). Extend that handler to route `storyboard.agent_*` events into local stepper state.

Add at the top of the `Board` component:

```tsx
import {
  AgentProgressStepper,
  INITIAL_AGENT_STEPS,
  type AgentSteps,
} from "./agent-progress-stepper";

// ...inside Board:
const [agentJobId, setAgentJobId] = useState<string | null>(null);
const [agentSteps, setAgentSteps] = useState<AgentSteps>(INITIAL_AGENT_STEPS);
const [showStepper, setShowStepper] = useState(false);
```

In the existing `connectEventStream` handler inside `Board`, add this AFTER the existing analyze/storyboard.regen routing:

```tsx
// New: storyboard.agent_* event routing for the active regenerate job
if ("job_id" in evt && agentJobId && evt.job_id === agentJobId) {
  if (evt.type === "storyboard.agent_started") {
    setShowStepper(true);  // first agent event mounts the stepper
    setAgentSteps((prev) => ({
      ...prev,
      [evt.stage]: { status: "active", summary: "" },
    }));
  } else if (evt.type === "storyboard.agent_complete") {
    setAgentSteps((prev) => ({
      ...prev,
      [evt.stage]: { status: "done", summary: evt.summary },
    }));
  } else if (evt.type === "storyboard.agent_failed") {
    setAgentSteps((prev) => ({
      ...prev,
      [evt.stage]: { status: "failed", summary: evt.reason },
    }));
  }
}
```

In the JSX, render the stepper above the sections:

```tsx
{showStepper && (
  <div className="mb-4">
    <AgentProgressStepper
      steps={agentSteps}
      onComplete={() => {
        setShowStepper(false);
        setAgentJobId(null);
        setAgentSteps(INITIAL_AGENT_STEPS);
      }}
    />
  </div>
)}
```

When `<RegenerateButton />` reports a new `job_id` (Step 3 below), reset state:

```tsx
const handleJobStarted = (jobId: string) => {
  setAgentJobId(jobId);
  setAgentSteps(INITIAL_AGENT_STEPS);
  // Note: we DON'T setShowStepper(true) here — only when the first agent_started event
  // arrives. If chronological_fallback is used (no API key), no agent events fire and
  // the stepper stays unmounted.
};

// pass to RegenerateButton:
<RegenerateButton projectId={projectId} onJobStarted={handleJobStarted} />
```

- [ ] **Step 3: Expose `job_id` from `regenerate-button.tsx`**

Read `desktop/web/src/components/board/regenerate-button.tsx`. If it already passes the job_id up via a callback (e.g. `onJobStarted`), you're done. Otherwise add an optional prop:

```tsx
export function RegenerateButton({
  projectId,
  onJobStarted,
}: {
  projectId: string;
  onJobStarted?: (jobId: string) => void;
}) {
  // ...
  const mutation = useMutation({
    mutationFn: () => api.regenerateStoryboard(projectId),
    onSuccess: (resp) => {
      onJobStarted?.(resp.job_id);
      // ... existing logic
    },
  });
  // ...
}
```

Then in `board.tsx`, pass the callback: `<RegenerateButton projectId={projectId} onJobStarted={setActiveJobId} />`.

- [ ] **Step 4: Typecheck + lint**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
npx --prefix desktop/web tsc --noEmit && npm --prefix desktop/web run lint
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add desktop/web/src/components/board/agent-progress-stepper.tsx desktop/web/src/components/board/board.tsx desktop/web/src/components/board/regenerate-button.tsx
git commit -m "$(cat <<'EOF'
feat(renderer): AgentProgressStepper for storyboard regenerate

Three-step horizontal indicator (Director → Editor → Polisher) that
appears above the storyboard sections when a multi-agent regenerate is
running. Each step transitions pending → active → done from WS events,
with checkmarks and subtitles. On any agent failure, the failed step
shows red with the reason and a "Falling back to chronological order"
note appears. Stepper unmounts ~800ms after the polisher completes.

RegenerateButton gains an optional onJobStarted callback so Board can
track the active job_id and mount the stepper for it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Inspector Murch readout

**Files:**
- Modify: `desktop/web/src/components/board/inspector-drawer.tsx`

- [ ] **Step 1: Open and modify `inspector-drawer.tsx`**

The existing inspector (read it first to confirm structure) renders label/in/out/preview controls for a selected segment. We need to:

1. Receive the parent clip's `analysis.scenes[]` so we can find the scene under the segment's `in_point`
2. Add a read-only block at the TOP of the drawer body showing the Murch score for that scene

Add a helper near the top of the file:

```tsx
import type { components } from "@/lib/api-types";
import { CompositeChip } from "@/components/clips/composite-chip";
import { DimensionBar } from "@/components/clips/dimension-bar";
import { SceneTypeChip } from "@/components/clips/scene-type-chip";

type ClipScene = components["schemas"]["ClipScene"];

function findSceneAtTime(scenes: ClipScene[], time: number): ClipScene | null {
  for (const s of scenes) {
    if (time >= s.start && time < s.end) return s;
  }
  return null;
}
```

Add a prop `clipScenes?: ClipScene[]` to the `InspectorDrawer` component. The Board (caller) passes the matching clip's scenes when it opens the drawer.

In the JSX render, before the existing form controls, add:

```tsx
{clipScenes && (() => {
  const scene = findSceneAtTime(clipScenes, segment.in_point);
  if (!scene) return null;
  if (!scene.murch) {
    return (
      <p className="text-xs text-[var(--color-placeholder)] italic mb-3">
        This scene hasn't been scored yet. Run "Score scenes" on the clips tab.
      </p>
    );
  }
  const m = scene.murch;
  return (
    <div className="mb-4 p-3 bg-[var(--color-background-alt)] rounded-md">
      <div className="flex items-center gap-2 mb-2">
        <SceneTypeChip type={m.scene_type} />
        <CompositeChip score={m.composite} />
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <DimRow label="Aesthetic" value={m.aesthetic} />
        <DimRow label="Credibility" value={m.credibility} />
        <DimRow label="Impact" value={m.impact} />
        <DimRow label="Memorability" value={m.memorability} />
        <DimRow label="Fun" value={m.fun} />
      </div>
      {m.rationale && (
        <p className="text-xs text-[var(--color-muted)] italic mt-2">
          "{m.rationale}"
        </p>
      )}
    </div>
  );
})()}
```

Add a small helper component at the bottom of the file:

```tsx
function DimRow({ label, value }: { label: string; value: number }) {
  return (
    <span className="flex items-center gap-2">
      <span className="text-[var(--color-muted)] w-20">{label}</span>
      <DimensionBar value={value} width={48} />
      <span className="font-semibold">{Math.round(value)}</span>
    </span>
  );
}
```

- [ ] **Step 2: Pass `clipScenes` from the Board to the drawer**

In `desktop/web/src/components/board/board.tsx`, where `<InspectorDrawer />` is rendered, find the matching clip in the clips list (probably from React Query cache or a fetched array) and pass its `analysis.scenes` to the drawer:

```tsx
const allClips = queryClient.getQueryData<ClipSummary[]>(["clips", projectId]);
const matchingClip = allClips?.find((c) =>
  // The segment's clip_path is a full filesystem path; the clip's filename is the basename
  segment.clip_path.endsWith(c.filename)
);

<InspectorDrawer
  segment={segment}
  // ... other existing props
  clipScenes={matchingClip?.analysis?.scenes ?? undefined}
/>
```

Adjust based on the actual existing data flow. The principle: get from `clip_path` → matching `ClipSummary` → `analysis.scenes[]`.

- [ ] **Step 3: Typecheck + lint**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
npx --prefix desktop/web tsc --noEmit && npm --prefix desktop/web run lint
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add desktop/web/src/components/board/inspector-drawer.tsx desktop/web/src/components/board/board.tsx
git commit -m "$(cat <<'EOF'
feat(renderer): Murch readout in segment inspector drawer

When a segment is selected in the storyboard board, the inspector
drawer shows the MurchScore for the source scene the segment's
in_point falls into: scene type chip, composite chip, all 5 dimension
bars with numeric labels, and the LLM rationale. When the scene has
no score, shows a one-line hint pointing to the score button.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Verify nothing else broke (full backend + renderer typecheck)

**Files:** None modified (verification only)

- [ ] **Step 1: Run the whole backend test suite**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m pytest 2>&1 | tail -20
```

Expected: All new tests pass; pre-existing failures (sentrysearch missing, pytest-asyncio missing) unchanged. The OpenAPI snapshot test should now PASS (regenerated in Task 5). If `test_score_route.py` from PR 3 fails, it's because Step 10 of Task 2 already updated it to async — should pass.

- [ ] **Step 2: Renderer typecheck + lint + build**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
npx --prefix desktop/web tsc --noEmit && npm --prefix desktop/web run lint && npm --prefix desktop/web run build
```

Expected: typecheck clean, lint clean, Next.js build succeeds.

- [ ] **Step 3: If any regressions are found, fix and commit**

Common regressions:
- A renderer file referenced `clip.analysis` as `unknown` and now needs to handle the typed shape
- A test that mocked `analysis: {}` now fails because the new shape requires specific keys

Read the failure, fix narrowly, commit.

---

## Task 12: Manual smoke test

**Files:** None modified (verification only)

- [ ] **Step 1: Start the desktop sidecar server**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
PYTHONPATH=src /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -m vlogkit.server --port 8421 &
SERVER_PID=$!
sleep 2
curl -s http://127.0.0.1:8421/healthz
```

Expected: `{"status": "ok"}` (or similar).

- [ ] **Step 2: Generate a synthetic project (reuse the Plan 1/2/3 helper)**

```bash
SMOKE=/tmp/vlogkit-smoke-uipr-$(date +%s)
mkdir -p "$SMOKE"
ffmpeg -y -f lavfi -i "color=c=red:s=320x240:d=4,format=yuv420p" \
  -f lavfi -i "color=c=green:s=320x240:d=4,format=yuv420p" \
  -f lavfi -i "color=c=blue:s=320x240:d=4,format=yuv420p" \
  -filter_complex "[0:v][1:v][2:v]concat=n=3:v=1[v]" -map "[v]" \
  -c:v libx264 -pix_fmt yuv420p -t 12 "$SMOKE/test_clip.mp4"
echo "$SMOKE" > /tmp/vlogkit-smoke-uipr.txt

cd "$SMOKE"
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src \
  /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -c "from vlogkit.cli import app; app()" init .
VLOGKIT_SEARCH_AUTO_INDEX=false PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src \
  /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -c "from vlogkit.cli import app; app()" analyze --no-vision --force
```

- [ ] **Step 3: Hit the score endpoint via curl to verify the async path**

Get the bearer token printed when the server started (from Step 1). Then:

```bash
TOKEN=...your token here...
# Register the project
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"path\": \"$SMOKE\"}" http://127.0.0.1:8421/projects

# List projects to get the project_id
PROJECT_ID=$(curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8421/projects | python -c "import sys, json; print(json.load(sys.stdin)[0]['id'])")
echo "Project: $PROJECT_ID"

# Score (will return 202 + job_id even with no API key — the job will publish ScoreFailed via WS quickly)
curl -X POST -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8421/projects/$PROJECT_ID/score
```

Expected: `{"job_id": "..."}`.

- [ ] **Step 4: Verify clips endpoint returns typed analysis**

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://127.0.0.1:8421/projects/$PROJECT_ID/clips | python -m json.tool | head -30
```

Expected: `analysis.scenes[]` with start/end/description/tags/keyframe_path/murch fields visible.

- [ ] **Step 5: Stop the server**

```bash
kill $SERVER_PID
```

- [ ] **Step 6: (Optional, requires GUI) Open the Electron app**

If you want to visually verify the UI:

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/desktop
npm run dev
```

Register the smoke project, click the new "Score scenes" button. Watch composite chips light up clip by clip. Click a clip card to see the inline scene rows. Click "Regenerate" on the board tab; if an API key is set, watch the Director→Editor→Polisher stepper progress.

This step is optional for the agent — the headless verification in Steps 1-5 is sufficient evidence the wiring works.

---

## Task 13: Push branch + open PR

- [ ] **Step 1: Push the branch**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
git push -u origin claude/desktop-ui-scores
```

- [ ] **Step 2: Open the PR (do NOT merge — wait for the user)**

```bash
gh pr create --title "feat(renderer): desktop UI for Murch scores + multi-agent progress" --body "$(cat <<'EOF'
## Summary
Surfaces the Murch scoring + multi-agent storyboard pipeline (PRs #1-3) in the desktop renderer.

**Backend:**
- `POST /projects/{id}/score` converted from sync → async (mirrors `/analyze`); returns `202 {job_id}`
- 5 new `score.*` WS events + 3 new `storyboard.agent_*` events
- `ClipSummary.analysis` typed: now exposes `scenes[].murch` directly

**Renderer:**
- `<ScoreButton />` next to `<AnalyzeButton />` on the clips tab
- Composite chip on each clip card (color-tiered: weak/mid/good/excellent ★)
- Click clip → inline expansion showing per-scene type chip + composite + 5-dim bars
- 3-step `<AgentProgressStepper />` above storyboard board during regenerate
- Murch readout in segment inspector drawer

**Live updates:** As scoring runs, composite chips refetch and update clip-by-clip via `score.clip_done` invalidation.

Spec: [`docs/superpowers/specs/2026-05-13-desktop-ui-scores-and-agent-progress-design.md`](docs/superpowers/specs/2026-05-13-desktop-ui-scores-and-agent-progress-design.md)
Plan: [`docs/superpowers/plans/2026-05-13-plan-desktop-ui-scores-and-agent-progress.md`](docs/superpowers/plans/2026-05-13-plan-desktop-ui-scores-and-agent-progress.md)

## Test plan
- [x] Backend unit tests: 9 event model tests, 2 score job tests, 4 score route tests, 2 builder agent-event tests, 1 clips-route shape test
- [x] OpenAPI snapshot regenerated to include new event models + typed analysis shape
- [x] Renderer: TypeScript typecheck clean, ESLint clean, Next.js production build succeeds
- [x] Headless smoke: server starts, `/projects/:id/score` returns 202 + job_id, `/projects/:id/clips` returns typed `analysis.scenes[].murch`
- [x] Pre-existing test failures (sentrysearch, pytest-asyncio) unchanged

## Out of scope
- Renderer unit test infrastructure (Vitest/Jest) — separate follow-up
- Project-local weight tuning UI
- Per-scene re-score button
- Scene-type filter on clips tab
- Score chips on board cards (only inspector for v1)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Capture the PR URL** for the user to review.

---

## Self-review checklist (before declaring done)

- [ ] Every step has actual code/commands; no placeholders or "implement appropriately" text
- [ ] Event type names use dot-separator consistently: `score.started`, `storyboard.agent_started` (matches existing `analyze.started`)
- [ ] `run_scoring` signature: `(project, force=False, progress_callback=None) -> int`
- [ ] `run_score_job` signature: `(broker, project_id, project, job_id, force=False) -> None` (async)
- [ ] `build_storyboard` signature: `(analyses, project_root, settings, strategy, context, event_callback=None) -> Storyboard`
- [ ] `ClipSummary.analysis` is `ClipAnalysisSummary | None` after Task 4
- [ ] `api.score(projectId, force=false)` returns `Promise<{job_id: string}>`
- [ ] All renderer imports use `@/` alias matching the existing convention
- [ ] CSS class names use the existing CSS-var palette (`var(--color-accent)` etc.) where the existing components do
- [ ] Spec coverage: §2 (backend) → Tasks 1-4; §3 (renderer) → Tasks 6-10; §4 (data flow) → wiring is correct; §5 (testing) → Tasks 1-4 cover it; §6 (rollout) → matches commit messages
- [ ] No deletions of pre-existing functionality (`chronological_fallback`, existing analyze flow, existing storyboard regen)
