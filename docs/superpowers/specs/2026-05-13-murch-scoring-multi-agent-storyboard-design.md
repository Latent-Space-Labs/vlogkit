# Murch-Style Scene Scoring + Multi-Agent Storyboard

**Date:** 2026-05-13
**Status:** Design — awaiting implementation plan
**Affects:** `src/vlogkit/analyze/`, `src/vlogkit/score/` (new), `src/vlogkit/storyboard/`, `src/vlogkit/models.py`, `src/vlogkit/config.py`, `src/vlogkit/cli.py`, `src/vlogkit/server/routes/`

---

## 1. Overview

Two coordinated changes to vlogkit's pipeline:

1. **Murch-style per-scene scoring** — a new `vlogkit score` command that grades each detected scene on 5 dimensions (aesthetic, credibility, impact, memorability, fun) with a scene-type-aware composite (hook/narrative/aesthetic/commercial). Inspired by Walter Murch's editing hierarchy as operationalized in [ALBEDO-TABAI/video-expert-analyzer](https://github.com/ALBEDO-TABAI/video-expert-analyzer) (methodology only — the repo has no license, no code is copied).
2. **Multi-agent storyboard generation** — replaces the existing single-shot `build_storyboard` LLM call with a Director → Editor → Polisher pipeline. Inspired by the multi-agent decomposition pattern in [HKUDS/ViMax](https://github.com/HKUDS/ViMax) (pattern only — ViMax targets video generation, not editing).

Both ideas slot into vlogkit's existing pipeline at distinct stages and share a downstream contract: scored scenes flow into the Editor agent, which picks them to fill the Director's section plan.

## 2. Background — research source materials

Three external repos were evaluated; only the two listed above contributed. The third — [digitalsamba/claude-code-video-toolkit](https://github.com/digitalsamba/claude-code-video-toolkit) — targets *generating* explainer videos (TTS, image gen, Remotion render) rather than assembling existing footage, and is out of scope for this spec. Some of its packaging patterns (Claude Code skills, brand profiles) may be revisited as a follow-on.

## 3. New pipeline shape

```
init → analyze → score → storyboard → review → export
              (NEW)
```

| Stage | What changes |
|---|---|
| `analyze` | Extended to also run scene detection (`analyze/scenes.py`) and keyframe vision (`analyze/vision.py`). These modules already exist but are not currently wired into `analyze_clip`. After this change, every cached `ClipAnalysis` has populated `scenes[]` with descriptions, tags, and `energy_score`. |
| `score` (new) | Reads cached `ClipAnalysis` files, runs a text-only Claude call per scene producing Murch scores, writes scores back into the same cache files. Idempotent; `--force` re-scores. |
| `storyboard` | Internal pipeline replaced. Same CLI surface and same output `Storyboard` schema. Now invokes Director → Editor → Polisher agents sequentially. |
| `review` | Unchanged. |
| `export` | Unchanged. |

The `chronological` no-LLM fallback in `storyboard/strategies.py` is preserved unchanged and remains the path used when `VLOGKIT_ANTHROPIC_API_KEY` is unset, or when any agent in the multi-agent flow fails.

## 4. Murch scoring details

### 4.1 Scene type taxonomy (4 types)

| Type | Definition |
|---|---|
| `hook` | Opens a section / grabs attention — big reveal, dramatic establishing shot, peak energy moment |
| `narrative` | Carries the story forward — spoken setup, transitional action, exposition |
| `aesthetic` | B-roll / atmosphere — pretty landscape, food close-up, ambient detail |
| `commercial` | Direct-to-camera, product/promo style — talking-head pitch, tutorial step |

### 4.2 Scoring dimensions (5)

All dimensions return floats in `[0, 100]`:

- `aesthetic` — visual composition, lighting, framing
- `credibility` — does it feel authentic and support the narrative
- `impact` — emotional punch, attention-grabbing power
- `memorability` — would a viewer remember this 10 minutes later
- `fun` — entertainment / delight factor

### 4.3 Weight tables (defaults)

Defined in `src/vlogkit/score/weights.py`. Weights per scene type sum to 1.0:

```python
WEIGHTS: dict[SceneType, dict[str, float]] = {
    "hook":       {"aesthetic": 0.10, "credibility": 0.05, "impact": 0.40, "memorability": 0.30, "fun": 0.15},
    "narrative":  {"aesthetic": 0.15, "credibility": 0.30, "impact": 0.20, "memorability": 0.20, "fun": 0.15},
    "aesthetic":  {"aesthetic": 0.50, "credibility": 0.10, "impact": 0.15, "memorability": 0.20, "fun": 0.05},
    "commercial": {"aesthetic": 0.25, "credibility": 0.20, "impact": 0.25, "memorability": 0.20, "fun": 0.10},
}
```

Composite score is computed locally: `composite = Σ(dimension_score × weight_for(scene_type, dimension))`. The LLM does not compute composite.

### 4.4 Project-local weight overrides

If `<project>/.vlogkit/score_weights.json` exists, it is loaded and merged over the defaults. Per-type partial overrides are allowed (missing keys fall back to default). Malformed JSON → warning printed, defaults used, no crash.

### 4.5 Scoring agent (`score/scorer.py`)

One text-only Claude call per scene. Inputs assembled from the cached `SceneSegment`:

- Scene description + tags (from wired-in vision step)
- Scene transcript slice (from clip transcript filtered by `scene.start..scene.end`)
- Scene duration + position-in-clip (e.g. "scene 2 of 4")
- Surrounding scene descriptions: one before, one after, for narrative context (when available)

Prompt asks for strict JSON:

```json
{
  "scene_type": "hook|narrative|aesthetic|commercial",
  "aesthetic": 0-100,
  "credibility": 0-100,
  "impact": 0-100,
  "memorability": 0-100,
  "fun": 0-100,
  "rationale": "one-line justification"
}
```

Returned JSON is parsed into a `MurchScore` Pydantic model. Composite is computed locally via the weight table for the returned `scene_type`. Result is attached to `SceneSegment.murch` and the parent `ClipAnalysis` is re-saved to its cache file.

Per-scene cost: approximately $0.003–0.005 with Claude Sonnet (text-only, ~1–2 K tokens per call).

### 4.6 Caching

- Lives inside existing `.vlogkit/clips/<hash>.json` — no new cache directories.
- `MurchScore | None` field is added to `SceneSegment`; old cached `ClipAnalysis` JSON loads cleanly with `murch=None`.
- `vlogkit score` default: skip scenes whose `murch` is already set; `--force` re-scores everything.
- `vlogkit score` requires `analyze` to have produced scenes; if no scenes are detected, the command prints an error pointing the user at `vlogkit analyze`.

## 5. Multi-agent storyboard details

### 5.1 Agents (3 sequential LLM calls)

#### Director (`storyboard/agents/director.py`)

**Input:**
- Project context string (CLI `-c "..."` argument)
- Strategy hint string (CLI `-s ...` argument — one of `chronological` / `energy-arc` / `thematic`, mapped to a hint via existing `STRATEGY_HINTS` dict)
- Aggregated scene-type counts across all clips (e.g. `{"hook": 12, "narrative": 18, "aesthetic": 25, "commercial": 5}`) — counts default to "unknown" if scenes lack `murch`
- Per-clip one-line summaries (filename + first-200-char `summary` field)

**Output JSON schema:**

```json
{
  "title": "string",
  "sections": [
    {
      "id": "s1",
      "title": "string",
      "goal": "string — what this section accomplishes",
      "target_duration": 30,
      "scene_types": ["hook"|"narrative"|"aesthetic"|"commercial", ...]
    }
  ],
  "arc_rationale": "string"
}
```

The Director never sees individual scenes — it sees *what is available in aggregate* and decides the shape.

#### Editor (`storyboard/agents/editor.py`)

**Input:**
- Director's full section plan
- Full list of scored scenes, each item: `{clip_path, scene_index, scene_type, composite, description, transcript_snippet, start, end, duration}`

**Output JSON schema:**

```json
{
  "assignments": [
    {
      "section_id": "s1",
      "picks": [
        {
          "clip_path": "string (basename)",
          "scene_index": 0,
          "in_point": 0.0,
          "out_point": 0.0,
          "reason": "string"
        }
      ]
    }
  ]
}
```

Editor responsibilities:
- For each section, pick scenes whose `scene_type` matches one in the section's `scene_types`
- Prefer higher composite scores
- Total duration of picks per section should target the section's `target_duration` (±25 %)
- `in_point` / `out_point` must lie inside the source scene's `[start, end]` range — orchestrator validates and clamps
- Avoid back-to-back scenes from the same clip unless explicitly justified in `reason`

Note on `scene_index`: this is the positional index of the scene within its parent clip's `scenes[]` list, not a field on `SceneSegment`. The orchestrator includes it in the prompt and uses `(clip_path, scene_index)` as the lookup key when validating picks. The Editor must echo the index back unchanged.

#### Polisher (`storyboard/agents/polisher.py`)

**Input:**
- Director plan
- Editor assignments
- Clip metadata (resolved by orchestrator from `ClipAnalysis`)

**Output JSON:** matches the existing `Storyboard` schema in `models.py` exactly — `{title, sections: [{title, notes, segments: [{clip_path, in_point, out_point, label, transition, include}]}], total_duration, llm_rationale}`.

Polisher responsibilities:
- Assign `transition` per segment based on scene-type adjacency heuristics (e.g. aesthetic→narrative often `dissolve`, hook→narrative often `cut`)
- Write viewer-facing one-line `label` per segment
- Compute `total_duration`
- Write the top-level `llm_rationale` summarizing editorial choices
- Set `include: true` by default; mark `include: false` only if a pick is redundant or contradicts the section goal

### 5.2 Orchestration (`storyboard/builder.py`)

Refactored shape:

```python
def build_storyboard(analyses, project_root, settings, strategy, context) -> Storyboard:
    if not settings.anthropic_api_key:
        console.print("[yellow]No API key found. Using chronological fallback.[/]")
        return chronological_fallback(analyses)
    try:
        plan = director.run(analyses, strategy, context, settings)
        assignments = editor.run(plan, analyses, settings)
        storyboard = polisher.run(plan, assignments, analyses, project_root, settings)
        return storyboard
    except AgentError as e:
        console.print(f"[yellow]Multi-agent flow failed at {e.stage}: {e}. Falling back to chronological order.[/]")
        return chronological_fallback(analyses)
```

Each agent module exposes a single `run(...)` function that wraps prompt formatting + `LLMBackend.complete` call + JSON parsing + Pydantic validation. Failures raise `AgentError(stage="director"|"editor"|"polisher", reason="...")`.

Per-stage progress is printed via `rich.console`:

```
[cyan]Director: planning narrative arc...[/]
[cyan]Editor: selecting scenes...[/]
[cyan]Polisher: finalizing transitions and labels...[/]
[green]Storyboard created: 5 sections, 23 segments[/]
```

### 5.3 When scores are missing

If `vlogkit score` was never run, all `SceneSegment.murch` are `None`. The flow still runs:

- Director receives `scene_type` counts as zero / unknown — it falls back to using description signals + transcript volume to plan sections
- Editor sees scenes without composite scores — it falls back to ordering by `energy_score` (already populated by `analyze`) and clip recency
- A one-time warning is printed at the start of `vlogkit storyboard`: `[yellow]Tip: run 'vlogkit score' for better scene selection.[/]`

Quality is meaningfully worse without scores but the pipeline produces a valid storyboard.

### 5.4 Why no revision loops in v1

Allowing Polisher to send work back to Editor (or Editor back to Director) introduces unbounded LLM-call counts and complicates the error model. Forward-only flow keeps:
- Cost predictable (exactly 3 calls per generation)
- Failure semantics simple (any stage fails → chronological fallback)
- Latency bounded (~30–60 s typical)

A future spec can add revision loops if v1's quality is not satisfactory.

## 6. Models, config, CLI, caching

### 6.1 Model changes (`src/vlogkit/models.py`)

```python
from typing import Literal

SceneType = Literal["hook", "narrative", "aesthetic", "commercial"]

class MurchScore(BaseModel):
    scene_type: SceneType
    aesthetic: float       # 0-100
    credibility: float
    impact: float
    memorability: float
    fun: float
    composite: float       # computed locally from weights
    rationale: str = ""

class SceneSegment(BaseModel):
    start: float
    end: float
    keyframe_path: Path | None = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    energy_score: float = 0.0
    murch: MurchScore | None = None    # NEW
```

Backward-compatible: the new field is optional with default `None`. Existing cache files load without migration.

### 6.2 Config additions (`src/vlogkit/config.py`)

```python
score_model: str = "claude-sonnet-4-20250514"          # VLOGKIT_SCORE_MODEL
storyboard_model: str = "claude-sonnet-4-20250514"     # VLOGKIT_STORYBOARD_MODEL (shared by Director/Editor/Polisher)
```

Two new settings. Director/Editor/Polisher share `storyboard_model` — per-agent model selection is out of scope for v1.

### 6.3 CLI surface (`src/vlogkit/cli.py`)

**New command:**

```
vlogkit score [-p PATH] [--force]
```

- `-p PATH` — project root override (same semantics as other commands)
- `--force` — re-score scenes even if `murch` is already set

**New flag on existing command:**

```
vlogkit analyze [--no-vision]
```

- `--no-vision` — skip wired-in vision step, leaving `description` and `tags` empty. Lets users opt out of the new cost. Default: vision runs.

**No CLI changes** to `storyboard`, `review`, or `export`. `vlogkit storyboard -s energy-arc -c "trip"` works identically — the multi-agent pipeline is internal.

### 6.4 File layout

```
src/vlogkit/
├── analyze/
│   ├── pipeline.py         # MODIFY — wire detect_scenes + describe_keyframe in
│   └── ...
├── score/                   # NEW package
│   ├── __init__.py
│   ├── scorer.py           # run_scoring(project) — orchestrates per-scene scoring
│   ├── prompts.py          # SCORING_PROMPT template
│   └── weights.py          # WEIGHTS dict + load_project_weights(project_root)
├── storyboard/
│   ├── builder.py          # MODIFY — orchestrate Director/Editor/Polisher
│   ├── prompts.py          # MODIFY — add per-agent prompt templates
│   ├── strategies.py       # unchanged (chronological_fallback stays)
│   └── agents/              # NEW
│       ├── __init__.py
│       ├── base.py         # AgentError, shared JSON parsing helpers
│       ├── director.py
│       ├── editor.py
│       └── polisher.py
└── cli.py                   # MODIFY — add `score` command, `--no-vision` flag
```

### 6.5 Server endpoint

Desktop-mode server (`src/vlogkit/server/`) adds one route:

```
POST /projects/:id/score      # triggers run_scoring(project), returns updated ClipAnalysis list
```

Auth: existing bearer-token. Implementation: thin wrapper around `score.scorer.run_scoring`.

Desktop renderer UI changes (displaying scores in clip viewer) are intentionally out of scope for this spec.

## 7. Testing strategy

| Area | Approach |
|---|---|
| `models.py` (new `MurchScore`, extended `SceneSegment`) | Round-trip via `.model_dump()` / `.model_validate()`. Assert old cache JSON (without `murch` key) loads with `murch=None`. |
| `score/weights.py` | Pure function — table-driven: known dimension scores × known scene type → expected composite. Test project-local override loading + malformed JSON warning. |
| `score/scorer.py` | Mock `LLMBackend.complete` with canned JSON (valid, malformed, missing keys, out-of-range values). Verify parsing, composite calculation, cache write, `--force` vs default behavior. |
| `storyboard/agents/director.py` | Mock backend. Verify scene-type aggregation, strategy hint injection, output schema validation. |
| `storyboard/agents/editor.py` | Mock backend. Verify section plan + scored scenes get formatted into prompt. Verify in/out points are clamped to source-scene bounds. Verify scene-type matching against `section.scene_types`. |
| `storyboard/agents/polisher.py` | Mock backend. Verify final `Storyboard` Pydantic validation. Verify default transition assignment. |
| `storyboard/builder.py` orchestration | Three mocked backends. Happy path: data flows correctly stage-to-stage. Failure path: each stage's `AgentError` falls back to `chronological_fallback`. |
| End-to-end CLI smoke | Tiny fixture project with 2 short clips. Stub `LLMBackend` at the protocol level. Run `analyze → score → storyboard`. Assert non-empty `Storyboard` with valid in/out points. |

Test files follow the existing `tests/test_*.py` layout. Approximately 8–12 new test files. No new test runners — pytest only.

## 8. Rollout — three PRs

Each PR is independently mergeable and reviewable:

### PR 1 — Wire vision + scenes into `analyze`

- Modify `analyze/pipeline.py` to call `detect_scenes()` and `describe_keyframe()` per clip
- Add `--no-vision` flag to `vlogkit analyze`
- No new commands, no new prompts, no model changes
- After merge: re-running `analyze` does vision calls for the first time (user-visible cost change — surface via console message)

### PR 2 — Add `vlogkit score`

- New `score/` package (scorer, prompts, weights)
- `MurchScore` model + `SceneSegment.murch` field
- `score_model` setting
- New `vlogkit score` CLI command
- Tests for models, weights, scorer
- Storyboard pipeline untouched — scoring is opt-in

### PR 3 — Multi-agent storyboard

- New `storyboard/agents/` package
- Refactor `storyboard/builder.py` orchestration
- New per-agent prompt templates in `storyboard/prompts.py`
- `storyboard_model` setting
- Tests for each agent + orchestration + fallback
- Server endpoint `POST /projects/:id/score` (small — included in this PR rather than a separate one)
- Existing CLI surface unchanged

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Agent returns malformed JSON | Strict Pydantic schema validation in each agent's `run()`. Any failure → `AgentError` → `chronological_fallback` with `[yellow]` warning naming the failing stage. |
| Latency: 3 sequential calls (~30–60 s) vs current single call (~10–15 s) | Per-stage progress messages via `rich.console`. Acceptable for an asynchronous, non-interactive command. |
| Wired-in vision adds cost users didn't expect | Console message during `analyze` ("Describing N keyframes via Claude vision (~$X)…"). `--no-vision` opt-out. Documented in CLAUDE.md update. |
| Default weight table is opinionated | Project-local `.vlogkit/score_weights.json` override. README documents tuning. |
| Tiny projects (< 5 scenes) get worse output from 3-agent pipeline than from a single call | Accept this for v1. Document in README that multi-agent benefits show on projects with ≥ 10 scenes. Revisit if real-world feedback shows a problem. |

## 10. Out of scope (v1)

- Revision loops between agents
- Per-agent model selection (Opus for Director, Haiku for Polisher, etc.)
- Desktop UI rendering of Murch scores in clip viewer (server endpoint only)
- Narration / voice-over script generation
- Music-sync / color-grade / b-roll-to-spoken-text matching
- Importing repo 2's (claude-code-video-toolkit) brand profiles, slash commands, or Remotion patterns
- Importing repo 3's (ViMax) Veo / Nano Banana generation tooling
