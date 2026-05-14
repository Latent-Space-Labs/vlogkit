# Desktop UI for Murch Scores + Multi-Agent Storyboard Progress

**Date:** 2026-05-13
**Status:** Design — awaiting implementation plan
**Affects:** `desktop/web/src/`, `src/vlogkit/server/`, `src/vlogkit/server/schemas.py`, `src/vlogkit/server/events.py`

---

## 1. Goal

Make the Murch scoring + multi-agent storyboard pipeline (shipped in PRs #1–3) **visible** in the desktop renderer. After this PR, opening a project surfaces:

- A composite score chip on each clip card, color-coded by tier
- A "Score scenes" button that runs scoring with live per-clip progress
- An expandable per-scene breakdown inline in the clip list (type chip + composite + 5-dim bars)
- A 3-step Director → Editor → Polisher progress banner during storyboard regenerate
- A read-only Murch readout in the existing segment inspector drawer

The backend `score` endpoint becomes async with WS events (mirroring `analyze`) so progress can stream live. The multi-agent storyboard pipeline emits new `agent_stage_*` WS events that drive the stepper.

## 2. Backend changes

### 2.1 `POST /projects/{id}/score` — sync → async

The endpoint added in PR #3 currently runs `run_scoring` synchronously and returns `{"scored": N}`. Convert to the async/threaded pattern used by `analyze`:

- Returns `202` with `{"job_id": str}` immediately
- Runs `run_scoring` in a thread (mirror `_run_job_in_thread` in `routes/analyze.py`)
- Publishes WS events via the broker as work progresses
- Same `?force=true` query param

The `run_scoring` orchestrator gains an optional `progress_callback` parameter. When set, it's called after each scene scored and after each clip's last scene completes. The route's job wrapper provides a callback that publishes events.

### 2.2 New WS events

Defined as Pydantic models in `src/vlogkit/server/events.py` (or wherever existing events live) so they show up in the OpenAPI snapshot.

**Score events:**

```python
{type: "score_started",   project_id, job_id, total_scenes}
{type: "score_progress",  project_id, job_id, scored, total_scenes, current_clip, current_scene_index}
{type: "score_clip_done", project_id, job_id, clip_filename, average_composite}
{type: "score_completed", project_id, job_id, total_scored}
{type: "score_failed",    project_id, job_id, reason}
```

`score_clip_done` fires when all of a clip's scenes finish; renderer uses it to invalidate that clip's `ClipSummary` query so the chip updates live.

**Multi-agent storyboard events:**

```python
{type: "agent_stage_started",   project_id, job_id, stage}                    # stage = "director"|"editor"|"polisher"
{type: "agent_stage_completed", project_id, job_id, stage, summary}
{type: "agent_stage_failed",    project_id, job_id, stage, reason}
```

`build_storyboard` already prints stage messages to console; wire those calls to also publish events. The publish callback is passed via an optional parameter and ignored when not in the server context (CLI continues to log to console only).

### 2.3 Typed `ClipSummary.analysis`

Today `analysis` is `{[key: string]: unknown} | null` — opaque to the renderer. Change the API response shape to:

```python
class ClipScene(BaseModel):                          # NEW — API-side schema (separate from internal SceneSegment)
    start: float
    end: float
    description: str = ""
    tags: list[str] = []
    keyframe_path: str | None = None
    murch: ClipMurchScore | None = None              # see below

class ClipMurchScore(BaseModel):                     # NEW
    scene_type: Literal["hook", "narrative", "aesthetic", "commercial"]
    aesthetic: float
    credibility: float
    impact: float
    memorability: float
    fun: float
    composite: float
    rationale: str = ""

class ClipAnalysisSummary(BaseModel):                # NEW — replaces the `unknown` shape
    scenes: list[ClipScene] = []
    summary: str = ""

class ClipSummary(BaseModel):                        # MODIFY existing
    # ...existing fields...
    analysis: ClipAnalysisSummary | None = None
```

The conversion from internal `ClipAnalysis` to the API `ClipSummary` happens in the existing `routes/clips.py` mapper.

## 3. Renderer architecture

### 3.1 New components

```
desktop/web/src/components/
├── clips/
│   ├── score-button.tsx           NEW — mirrors analyze-button.tsx
│   ├── scene-row.tsx              NEW — single scene's display in expanded clip
│   ├── scene-type-chip.tsx        NEW — small reusable chip with semantic colors
│   ├── composite-chip.tsx         NEW — color-tiered score chip
│   ├── dimension-bar.tsx          NEW — small inline horizontal bar for one of the 5 dims
│   └── clip-card.tsx              MODIFY — add chip + expand affordance
└── board/
    ├── agent-progress-stepper.tsx NEW — 3-step Director/Editor/Polisher banner
    └── inspector-drawer.tsx       MODIFY — add Murch readout
```

### 3.2 Score button (`score-button.tsx`)

Mirrors `analyze-button.tsx`. Lives in the clips tab toolbar next to the analyze button.

```tsx
<ScoreButton projectId={id} />
```

States: `idle | running | completed | failed`. While running: button text becomes "Scoring 14 of 24…" with a thin progress strip beneath. Disabled when no clips have been analyzed yet (since scoring requires scenes).

### 3.3 Composite chip (`composite-chip.tsx`)

Color tiers (numeric thresholds, configurable later):

| Composite | Background | Text | Notes |
|---|---|---|---|
| 0–49 | red bg | dark red text | "weak" |
| 50–69 | amber bg | dark amber text | "mid" |
| 70–84 | emerald bg | dark emerald text | "good" |
| 85–100 | gold bg | dark gold text | ★ prefix flourish |

Mixed-state suffix `(2/3)` when only some scenes are scored. No chip when zero scenes scored.

### 3.4 Scene-type chip (`scene-type-chip.tsx`)

| Type | Background | Text |
|---|---|---|
| hook | blue-100 | blue-900 |
| narrative | amber-100 | amber-900 |
| aesthetic | emerald-100 | emerald-900 |
| commercial | purple-100 | purple-900 |

(Map to the project's CSS-var palette in `DESIGN.md` — adjust class names accordingly.)

### 3.5 Clip card (`clip-card.tsx`)

Adds:
- Composite chip in the header row (between filename and status pill)
- `▾`/`▸` expand caret left of the filename when scenes exist
- Click anywhere on the header → toggles expanded state (uncontrolled, local component state)
- Expanded: per-scene table renders below the existing meta line. Each row uses `<SceneRow />`.

When a clip has zero scored scenes (analyzed but never scored), expanded state shows: *"No scores yet. Run 'Score scenes' to grade."*

### 3.6 Scene row (`scene-row.tsx`)

Compact horizontal layout:

```
[time]   [SceneTypeChip]   [composite]   [DimensionBar × 5]
0–4s     [hook]            87            ▓▓▁▆▅▃
```

Reads from `clip.analysis.scenes[i]`. The 5 bars are ordered: aesthetic, credibility, impact, memorability, fun. Each bar is `<DimensionBar value={number} />` (0–100 → bar length).

### 3.7 Agent progress stepper (`agent-progress-stepper.tsx`)

```tsx
<AgentProgressStepper jobId={jobId} onComplete={() => …} onFailure={(stage, reason) => …} />
```

Three steps: Director, Editor, Polisher. Each step has four visual states:
- `pending` — gray circle + step number
- `active` — blue circle + spinner, blue subtitle text
- `done` — green circle + checkmark, neutral subtitle showing `summary` from `agent_stage_completed`
- `failed` — red circle + ✕, red subtitle with `reason`

Mounted by `Board` only after the first `agent_stage_started` event for the active `jobId`. If 3 seconds elapse without one (chronological-fallback path), the stepper stays unmounted and the existing spinner-only behavior applies.

After `storyboard_completed` or `storyboard_failed`, persists for ~5 seconds then fades out. Subsequent regenerates spawn a fresh stepper.

### 3.8 Inspector Murch readout (`inspector-drawer.tsx`)

Adds a read-only block at the top showing the MurchScore for the scene the segment's `in_point` falls into. Renderer infers the scene_index by finding the scene whose `[start, end]` brackets the `in_point`.

```
[hook]   ★ 87
Aesthetic    ▓▓▓░░ 80
Credibility  ▓▓▒░░ 70
Impact       ▓▓▓▓▒ 90
Memorability ▓▓▓▓░ 85
Fun          ▓▓▒░░ 60
"strong opener with clear narrative hook"
```

If `murch` is null for that scene: *"This scene hasn't been scored yet. Run 'Score scenes' on the clips tab."*

### 3.9 Events reducer (`lib/events.ts`)

Extend the discriminated union:

```ts
type Event =
  | AnalyzeStarted | AnalyzeProgress | AnalyzeCompleted | AnalyzeFailed
  | ScoreStarted | ScoreProgress | ScoreClipDone | ScoreCompleted | ScoreFailed     // NEW
  | StoryboardStarted | StoryboardCompleted | StoryboardFailed
  | AgentStageStarted | AgentStageCompleted | AgentStageFailed                       // NEW
```

The existing per-job state tracking (keyed by `job_id`) continues to work without restructuring.

### 3.10 API client (`lib/api.ts`)

Add:

```ts
score: (projectId: string, force = false) =>
  request<{ job_id: string }>(`/projects/${projectId}/score${force ? "?force=true" : ""}`, {
    method: "POST",
  }),
```

### 3.11 Type regeneration (`lib/api-types.ts`)

Regenerated by the project's existing openapi-typescript script after backend changes. Committed alongside renderer changes.

## 4. Data flow

### 4.1 Score flow

```
[user clicks "Score scenes"]
   ↓
ScoreButton.api.score(projectId)
   ↓ POST /projects/:id/score → 202 {job_id}
   ↓
Server score-job thread:
   for each clip:
     for each scene:
       call run_scoring scene's score_scene
       publish score_progress
     publish score_clip_done {clip_filename, average_composite}
   publish score_completed
   ↓
Renderer:
   useProjectEvents reducer reads each event
   ScoreButton updates "Scoring N of M…" from score_progress
   On score_clip_done → React Query invalidates clips/{projectId} → ClipCard refetches → composite chip updates live
   On score_completed → ScoreButton returns to idle
```

### 4.2 Multi-agent storyboard flow

```
[user clicks "Regenerate"]
   ↓
RegenerateButton → api.regenerateStoryboard(projectId) → 202 {job_id}
   ↓
Server storyboard-job thread runs build_storyboard:
   if no API key: chronological_fallback (no agent events) → storyboard_completed
   else:
     publish agent_stage_started {stage: "director"}
     run director → publish agent_stage_completed {stage: "director", summary: "Planned 4 sections"}
     publish agent_stage_started {stage: "editor"}
     run editor → publish agent_stage_completed {stage: "editor", summary: "Picked 12 segments"}
     publish agent_stage_started {stage: "polisher"}
     run polisher → publish agent_stage_completed {stage: "polisher", summary: "Storyboard ready"}
     publish storyboard_completed
   on AgentError at stage X:
     publish agent_stage_failed {stage: X, reason: "..."}
     fall back to chronological_fallback → publish storyboard_completed
   ↓
Renderer:
   Board mounts AgentProgressStepper after first agent_stage_started event
   Stepper advances through stages on agent_stage_completed events
   On storyboard_completed → board refetches storyboard, stepper fades after 5s
   On agent_stage_failed → step shows failed state + reason; downstream stays pending
```

## 5. Testing strategy

| Area | Approach |
|---|---|
| Backend — async score job | New `tests/server/test_score_job.py`. Mock `run_scoring` with a callback-emitter, drive the threaded job, assert events published. Test `score_failed` on exception. Test `force` param threads through. |
| Backend — agent stage events | Extend `tests/test_storyboard_builder.py`. Mock the WS broker; verify `build_storyboard` publishes `agent_stage_*` events per stage including failure path. |
| Backend — typed `ClipSummary.analysis` | Update or add `tests/server/test_clips_route.py`. Verify response includes typed `scenes[]` with optional `murch`. |
| Renderer — primitives | Vitest + RTL. Per-component: `<CompositeChip />` color tier mapping (test boundary values 49/50/69/70/84/85), `<SceneTypeChip />` color mapping per type, `<DimensionBar />` width scaling, `<SceneRow />` rendering with mocked data. |
| Renderer — `<ScoreButton />` | Test idle → running → completed transitions on mocked events. Test disabled state when no clips analyzed. |
| Renderer — clip card expand | Test that clicking expands inline, that scenes render with `murch` data, that empty-state message appears when all `murch` are null. |
| Renderer — `<AgentProgressStepper />` | Inject sequenced events; assert state transitions per step. Test failure state. Test 90s timeout fallback. |
| Renderer — inspector Murch readout | Test readout for segment with scored scene. Test empty hint when `murch` is null. Test `scene_index` inference from `in_point`. |
| Renderer — events reducer | Unit tests for new event types: shape validation, job-id routing. |
| End-to-end (manual smoke) | Start desktop app, register a synthetic project, click "Score scenes" (mocked backend if no API key), watch chips light up clip by clip. Click "Regenerate", watch stepper progress through 3 stages. |

## 6. Rollout — single PR, 9 commits

1. `feat(server): convert score endpoint to async + emit score_* events`
2. `feat(server): emit agent_stage_* events from build_storyboard`
3. `feat(server): typed scenes/murch in ClipSummary.analysis`
4. `chore(types): regenerate api-types.ts`
5. `feat(renderer): CompositeChip + SceneTypeChip + DimensionBar + SceneRow primitives`
6. `feat(renderer): ScoreButton + clip card expand for scores`
7. `feat(renderer): AgentProgressStepper for storyboard regenerate`
8. `feat(renderer): Murch readout in segment inspector`
9. `chore(events): wire new event types into useProjectEvents reducer`

Reviewable in order. Each commit produces a passing test suite.

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| OpenAPI regeneration introduces unrelated diff churn | Isolate as a single commit (#4) so reviewers can verify shape additions without scanning unrelated formatting changes. |
| `score_clip_done` race causing stale UI | Use React Query invalidation rather than direct cache mutation; the refetch is the source of truth. |
| Stepper persists indefinitely if `storyboard_completed` event is lost | 90-second timeout; on expiry, fades out and surfaces a small "Lost connection — refresh storyboard?" banner. |
| Score progress event spam slows broker | Bounded — one event per scene scored, ~30–90 per project, well under throughput. |
| Pre-existing OpenAPI snapshot test still failing (from PR #1 baseline) | Will need regeneration as part of commit #4. Note in PR description that drift is intentional. |
| Color-tier thresholds (0/50/70/85) feel wrong in practice | Tune by observation; the thresholds live in `composite-chip.tsx` as constants. |
| Scene_index inference in inspector is fragile if scenes change after segment creation | Inference is read-only and best-effort; if no scene brackets the in_point, the readout shows the empty hint instead of guessing. |

## 8. Out of scope (v1)

- Project-local weight tuning UI (edit `.vlogkit/score_weights.json` from settings)
- Per-scene re-score button (currently only project-wide `--force`)
- Scene-type filter on the clips tab
- Per-segment score chips on the storyboard board cards (only inspector for v1)
- Live transcript scrubbing in the inspector
- Scene-type aggregate counts on the project header (e.g. "12 hooks / 18 narrative / 25 aesthetic")
- "Sort by score" toggle on the clips list
