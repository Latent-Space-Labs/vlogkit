# Plan 2 — `vlogkit score` command + Murch scoring (PR 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `vlogkit score` CLI command that grades every detected scene on five Murch-style dimensions (aesthetic, credibility, impact, memorability, fun) with scene-type-aware weighted composites. Scores are stored on `SceneSegment.murch` and cached alongside the existing `ClipAnalysis`.

**Architecture:** New `score/` package with three files (`weights.py`, `prompts.py`, `scorer.py`). The scorer makes one text-only Claude call per scene using cached descriptions, tags, and transcript slices — no new vision calls. Composite scores are computed locally from the LLM's per-dimension scores via type-specific weight tables. A project-local `.vlogkit/score_weights.json` can override defaults.

**Tech Stack:** Python 3.11+, pytest, pydantic, anthropic SDK (existing), typer (existing).

**Spec reference:** [`docs/superpowers/specs/2026-05-13-murch-scoring-multi-agent-storyboard-design.md`](../specs/2026-05-13-murch-scoring-multi-agent-storyboard-design.md) §4 (Murch scoring), §6.1–6.3 (models, config, CLI), §8 PR 2.

---

## File map

**Create:**
- `src/vlogkit/score/__init__.py` — empty package init
- `src/vlogkit/score/weights.py` — `WEIGHTS` dict, `composite_score()`, `load_project_weights()`
- `src/vlogkit/score/prompts.py` — `SCORING_PROMPT` and `SYSTEM_PROMPT`
- `src/vlogkit/score/scorer.py` — `score_scene()` and `run_scoring()`
- `tests/test_score.py` — unit tests for the entire `score/` package

**Modify:**
- `src/vlogkit/models.py` — add `SceneType` Literal, `MurchScore` Pydantic model, extend `SceneSegment` with optional `murch: MurchScore | None`
- `src/vlogkit/config.py` — add `score_model` setting
- `src/vlogkit/cli.py` — add the `score` Typer command
- `tests/test_models.py` — add backward-compatibility test for old cache JSON

---

## Task 1: Add `MurchScore` model and extend `SceneSegment`

**Files:**
- Modify: `src/vlogkit/models.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_models.py`:

```python
def test_scene_segment_default_murch_is_none():
    """SceneSegment.murch defaults to None — backward compat with old cache files."""
    from vlogkit.models import SceneSegment

    scene = SceneSegment(start=0.0, end=5.0)
    assert scene.murch is None


def test_scene_segment_loads_old_cache_without_murch_key():
    """Old cached JSON (pre-Plan-2) lacking 'murch' key still loads cleanly."""
    from vlogkit.models import SceneSegment

    old_json = {"start": 0.0, "end": 5.0, "description": "old", "tags": ["a"], "energy_score": 0.5}
    scene = SceneSegment.model_validate(old_json)
    assert scene.murch is None
    assert scene.description == "old"


def test_murch_score_round_trip():
    """MurchScore serializes and deserializes cleanly with all required fields."""
    from vlogkit.models import MurchScore

    score = MurchScore(
        scene_type="hook",
        aesthetic=80.0,
        credibility=70.0,
        impact=90.0,
        memorability=85.0,
        fun=60.0,
        composite=82.5,
        rationale="strong opener",
    )
    dumped = score.model_dump()
    assert dumped["scene_type"] == "hook"
    assert dumped["composite"] == 82.5

    reloaded = MurchScore.model_validate(dumped)
    assert reloaded == score


def test_murch_score_rejects_invalid_scene_type():
    """SceneType is constrained to four literals."""
    import pytest
    from pydantic import ValidationError

    from vlogkit.models import MurchScore

    with pytest.raises(ValidationError):
        MurchScore(
            scene_type="invalid",  # type: ignore[arg-type]
            aesthetic=0, credibility=0, impact=0, memorability=0, fun=0, composite=0,
        )


def test_scene_segment_serializes_with_murch():
    """SceneSegment with a MurchScore round-trips through JSON."""
    from vlogkit.models import MurchScore, SceneSegment

    scene = SceneSegment(
        start=0.0, end=5.0,
        murch=MurchScore(
            scene_type="aesthetic", aesthetic=90, credibility=50, impact=40,
            memorability=70, fun=20, composite=68.5,
        ),
    )
    dumped_json = scene.model_dump_json()
    reloaded = SceneSegment.model_validate_json(dumped_json)
    assert reloaded.murch is not None
    assert reloaded.murch.scene_type == "aesthetic"
    assert reloaded.murch.composite == 68.5
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_models.py -v
```

Expected: at least one FAIL with `ImportError` or `AttributeError` because `MurchScore` doesn't exist and `SceneSegment` lacks `murch`.

- [ ] **Step 3: Add `SceneType`, `MurchScore`, and the `murch` field**

In `src/vlogkit/models.py`, add `from typing import Literal` to the imports (or extend the existing typing import), and insert the following near the other model definitions (a sensible spot is right after `SceneSegment` is currently defined — but we'll modify `SceneSegment` itself to include `murch`).

Replace the existing `SceneSegment` definition with:

```python
SceneType = Literal["hook", "narrative", "aesthetic", "commercial"]


class MurchScore(BaseModel):
    scene_type: SceneType
    aesthetic: float       # 0-100
    credibility: float
    impact: float
    memorability: float
    fun: float
    composite: float       # computed locally from weights, not asked from LLM
    rationale: str = ""


class SceneSegment(BaseModel):
    start: float
    end: float
    keyframe_path: Path | None = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    energy_score: float = 0.0
    murch: MurchScore | None = None
```

Make sure `Literal` is imported. Existing import block currently has `from datetime import datetime` and `from pathlib import Path`; add `from typing import Literal` if it's not already there.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_models.py -v
```

Expected: all tests pass (existing + 5 new).

- [ ] **Step 5: Commit**

```bash
git add src/vlogkit/models.py tests/test_models.py
git commit -m "$(cat <<'EOF'
feat(models): add MurchScore and SceneSegment.murch field

Adds the SceneType literal (hook/narrative/aesthetic/commercial) and
MurchScore Pydantic model with five 0-100 dimension scores plus a
locally-computed composite. SceneSegment gains an optional murch field
that defaults to None — old cache JSON loads without migration.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add `score/weights.py` — default weights and project override loader

**Files:**
- Create: `src/vlogkit/score/__init__.py`
- Create: `src/vlogkit/score/weights.py`
- Create: `tests/test_score.py`

- [ ] **Step 1: Add the failing tests**

Create `tests/test_score.py`:

```python
"""Unit tests for the score/ package."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vlogkit.score.weights import (
    DEFAULT_WEIGHTS,
    composite_score,
    load_project_weights,
)


def test_default_weights_each_type_sums_to_one():
    """Every scene-type weight table must sum to 1.0 within float tolerance."""
    for scene_type, weights in DEFAULT_WEIGHTS.items():
        total = sum(weights.values())
        assert abs(total - 1.0) < 1e-6, f"{scene_type} weights sum to {total}, not 1.0"


def test_default_weights_have_all_five_dimensions():
    """Every scene type must weight all five dimensions."""
    expected = {"aesthetic", "credibility", "impact", "memorability", "fun"}
    for scene_type, weights in DEFAULT_WEIGHTS.items():
        assert set(weights.keys()) == expected, f"{scene_type} missing dimensions"


def test_composite_score_hook_with_uniform_70():
    """A hook scoring 70 on every dimension has composite = 70 (since weights sum to 1)."""
    result = composite_score(
        scene_type="hook",
        scores={"aesthetic": 70, "credibility": 70, "impact": 70, "memorability": 70, "fun": 70},
        weights=DEFAULT_WEIGHTS,
    )
    assert abs(result - 70.0) < 1e-6


def test_composite_score_hook_emphasizes_impact():
    """Hook weights impact at 0.40, so a high-impact scene scores higher than a low-impact one."""
    high_impact = composite_score(
        "hook",
        {"aesthetic": 50, "credibility": 50, "impact": 100, "memorability": 50, "fun": 50},
        DEFAULT_WEIGHTS,
    )
    low_impact = composite_score(
        "hook",
        {"aesthetic": 50, "credibility": 50, "impact": 0, "memorability": 50, "fun": 50},
        DEFAULT_WEIGHTS,
    )
    assert high_impact > low_impact
    # The 100-vs-0 swing on a 0.40-weighted dimension is exactly 40 points
    assert abs((high_impact - low_impact) - 40.0) < 1e-6


def test_composite_score_unknown_scene_type_raises():
    """Passing a scene_type not in the weights dict raises KeyError."""
    with pytest.raises(KeyError):
        composite_score("unknown", {"aesthetic": 50, "credibility": 50, "impact": 50, "memorability": 50, "fun": 50}, DEFAULT_WEIGHTS)


def test_load_project_weights_no_override_file_returns_defaults(tmp_path):
    """When .vlogkit/score_weights.json is absent, defaults are returned unchanged."""
    project_root = tmp_path
    (project_root / ".vlogkit").mkdir()

    weights = load_project_weights(project_root)
    assert weights == DEFAULT_WEIGHTS


def test_load_project_weights_full_override(tmp_path):
    """A complete override JSON replaces all four scene types."""
    project_root = tmp_path
    cache = project_root / ".vlogkit"
    cache.mkdir()
    override = {
        "hook":       {"aesthetic": 0.10, "credibility": 0.10, "impact": 0.50, "memorability": 0.20, "fun": 0.10},
        "narrative":  {"aesthetic": 0.20, "credibility": 0.20, "impact": 0.20, "memorability": 0.20, "fun": 0.20},
        "aesthetic":  {"aesthetic": 0.60, "credibility": 0.10, "impact": 0.10, "memorability": 0.10, "fun": 0.10},
        "commercial": {"aesthetic": 0.20, "credibility": 0.20, "impact": 0.20, "memorability": 0.20, "fun": 0.20},
    }
    (cache / "score_weights.json").write_text(json.dumps(override))

    loaded = load_project_weights(project_root)
    assert loaded["hook"]["impact"] == 0.50
    assert loaded["narrative"]["aesthetic"] == 0.20


def test_load_project_weights_partial_override_falls_back_to_defaults(tmp_path):
    """Partial overrides only replace the listed scene types; others keep defaults."""
    project_root = tmp_path
    cache = project_root / ".vlogkit"
    cache.mkdir()
    partial = {"hook": {"aesthetic": 0.10, "credibility": 0.10, "impact": 0.50, "memorability": 0.20, "fun": 0.10}}
    (cache / "score_weights.json").write_text(json.dumps(partial))

    loaded = load_project_weights(project_root)
    assert loaded["hook"]["impact"] == 0.50
    assert loaded["narrative"] == DEFAULT_WEIGHTS["narrative"]


def test_load_project_weights_malformed_json_returns_defaults_with_warning(tmp_path, capsys):
    """Malformed override JSON is logged and defaults are used (no crash)."""
    project_root = tmp_path
    cache = project_root / ".vlogkit"
    cache.mkdir()
    (cache / "score_weights.json").write_text("{ this is not json")

    loaded = load_project_weights(project_root)
    assert loaded == DEFAULT_WEIGHTS
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_score.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'vlogkit.score'`.

- [ ] **Step 3: Create `src/vlogkit/score/__init__.py`**

Create an empty file:

```python
"""Murch-style per-scene scoring."""
```

- [ ] **Step 4: Create `src/vlogkit/score/weights.py`**

Create with this exact content:

```python
"""Default weights, composite calculation, and project-local overrides for Murch scoring."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from rich.console import Console

from ..models import SceneType

console = Console()


DEFAULT_WEIGHTS: dict[SceneType, dict[str, float]] = {
    "hook":       {"aesthetic": 0.10, "credibility": 0.05, "impact": 0.40, "memorability": 0.30, "fun": 0.15},
    "narrative":  {"aesthetic": 0.15, "credibility": 0.30, "impact": 0.20, "memorability": 0.20, "fun": 0.15},
    "aesthetic":  {"aesthetic": 0.50, "credibility": 0.10, "impact": 0.15, "memorability": 0.20, "fun": 0.05},
    "commercial": {"aesthetic": 0.25, "credibility": 0.20, "impact": 0.25, "memorability": 0.20, "fun": 0.10},
}


def composite_score(
    scene_type: str,
    scores: Mapping[str, float],
    weights: Mapping[str, Mapping[str, float]],
) -> float:
    """Weighted sum of dimension scores using the table for the given scene_type."""
    table = weights[scene_type]  # KeyError if scene_type unknown — caller's bug
    return sum(table[dim] * scores[dim] for dim in table)


def load_project_weights(project_root: Path) -> dict[SceneType, dict[str, float]]:
    """Load `.vlogkit/score_weights.json` overrides, falling back to DEFAULT_WEIGHTS.

    Partial overrides are merged with defaults: if the JSON only specifies some
    scene types, the other types keep their default weights. Malformed JSON
    triggers a warning and returns the defaults unchanged.
    """
    override_path = project_root / ".vlogkit" / "score_weights.json"
    if not override_path.exists():
        return {k: dict(v) for k, v in DEFAULT_WEIGHTS.items()}

    try:
        override = json.loads(override_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[yellow]score_weights.json could not be loaded ({e}); using defaults.[/]")
        return {k: dict(v) for k, v in DEFAULT_WEIGHTS.items()}

    merged: dict[SceneType, dict[str, float]] = {k: dict(v) for k, v in DEFAULT_WEIGHTS.items()}
    for scene_type, dim_weights in override.items():
        if scene_type in merged and isinstance(dim_weights, dict):
            merged[scene_type] = dict(dim_weights)
    return merged
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_score.py -v
```

Expected: all 9 weights tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/vlogkit/score/__init__.py src/vlogkit/score/weights.py tests/test_score.py
git commit -m "$(cat <<'EOF'
feat(score): add weight tables and composite calculator

Default weights per Murch scene type (hook/narrative/aesthetic/commercial)
sum to 1.0 across the five dimensions. composite_score computes the
weighted sum locally so the LLM never has to do math. Project-local
.vlogkit/score_weights.json overrides are merged with defaults; missing
scene types fall back to defaults; malformed JSON warns and uses defaults.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add `score/prompts.py` — the scoring prompt template

**Files:**
- Create: `src/vlogkit/score/prompts.py`

- [ ] **Step 1: Create the prompts file (no test needed — pure data)**

Create `src/vlogkit/score/prompts.py`:

```python
"""Prompt templates for Murch-style scene scoring."""

SYSTEM_PROMPT = """\
You are a video editor scoring scenes for use in a vlog.

Given a scene's description, transcript, duration, and surrounding context, \
classify its narrative role and rate it on five dimensions. \
Return strict JSON only — no markdown, no preamble, no explanation outside the JSON."""


SCORING_PROMPT = """\
Score this scene from a video clip:

Scene {scene_index} of {scene_count} in clip "{clip_filename}"
Time: {start:.1f}s – {end:.1f}s ({duration:.1f}s)
Visual description: {description}
Tags: {tags}
Transcript: {transcript}
Previous scene description: {prev_description}
Next scene description: {next_description}

Classify scene_type as ONE of:
- "hook": opens or grabs attention (big reveal, dramatic shot, peak energy)
- "narrative": carries the story (spoken setup, transitional action, exposition)
- "aesthetic": b-roll / atmosphere (landscape, food close-up, ambient detail)
- "commercial": direct-to-camera, product/promo style (talking head pitch)

Score these five dimensions on 0-100:
- aesthetic: visual composition, lighting, framing
- credibility: authenticity and narrative-supporting feel
- impact: emotional punch, attention-grabbing power
- memorability: would a viewer remember this 10 minutes later
- fun: entertainment / delight factor

Respond with valid JSON exactly matching this schema:
{{
  "scene_type": "hook|narrative|aesthetic|commercial",
  "aesthetic": 0,
  "credibility": 0,
  "impact": 0,
  "memorability": 0,
  "fun": 0,
  "rationale": "one-line justification (under 20 words)"
}}"""
```

- [ ] **Step 2: Confirm the file is parsable**

```bash
PYTHONPATH=src .venv/bin/python -c "from vlogkit.score.prompts import SCORING_PROMPT, SYSTEM_PROMPT; print(len(SCORING_PROMPT), len(SYSTEM_PROMPT))"
```

Expected: two integers printed (the byte counts of the templates). No exception.

- [ ] **Step 3: Commit**

```bash
git add src/vlogkit/score/prompts.py
git commit -m "$(cat <<'EOF'
feat(score): add Murch scoring prompt template

Single text-only prompt asks Claude to classify scene_type and score
five 0-100 dimensions (aesthetic/credibility/impact/memorability/fun)
plus a one-line rationale. Composite is computed locally from the
returned dimension scores — never asked from the model.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add `score/scorer.py::score_scene()` — single-scene scoring agent

**Files:**
- Create: `src/vlogkit/score/scorer.py`
- Modify: `tests/test_score.py`

- [ ] **Step 1: Append the failing tests to `tests/test_score.py`**

Add these tests at the bottom of `tests/test_score.py`:

```python
def _make_scene_with_context(idx: int, description: str = "a description"):
    """Build a SceneSegment with sane defaults for scoring tests."""
    from vlogkit.models import SceneSegment
    return SceneSegment(start=idx * 5.0, end=(idx + 1) * 5.0, description=description, tags=["t1"])


def test_score_scene_parses_valid_response(monkeypatch):
    """A valid JSON response from the LLM produces a MurchScore with composite computed locally."""
    from vlogkit.config import Settings
    from vlogkit.score.scorer import score_scene

    captured_prompts: list[str] = []

    class FakeBackend:
        def complete(self, prompt: str, system: str = "") -> str:
            captured_prompts.append(prompt)
            return '{"scene_type": "hook", "aesthetic": 80, "credibility": 70, "impact": 90, "memorability": 85, "fun": 60, "rationale": "strong opener"}'

    settings = Settings(anthropic_api_key="test-key")
    scenes = [_make_scene_with_context(0), _make_scene_with_context(1), _make_scene_with_context(2)]

    score = score_scene(
        scene=scenes[1], scene_index=1, scenes=scenes,
        clip_filename="clip.mp4", transcript_text="hello",
        backend=FakeBackend(), weights=None,
    )
    assert score.scene_type == "hook"
    assert score.impact == 90
    # Hook composite: 0.10*80 + 0.05*70 + 0.40*90 + 0.30*85 + 0.15*60 = 8 + 3.5 + 36 + 25.5 + 9 = 82.0
    assert abs(score.composite - 82.0) < 1e-6
    assert score.rationale == "strong opener"
    assert len(captured_prompts) == 1


def test_score_scene_strips_markdown_fence(monkeypatch):
    """Some LLM responses wrap JSON in ```json ... ``` fences. The scorer must tolerate that."""
    from vlogkit.config import Settings
    from vlogkit.score.scorer import score_scene

    class FakeBackend:
        def complete(self, prompt: str, system: str = "") -> str:
            return '```json\n{"scene_type": "narrative", "aesthetic": 50, "credibility": 50, "impact": 50, "memorability": 50, "fun": 50, "rationale": "ok"}\n```'

    settings = Settings(anthropic_api_key="test-key")
    scenes = [_make_scene_with_context(0)]

    score = score_scene(
        scene=scenes[0], scene_index=0, scenes=scenes,
        clip_filename="clip.mp4", transcript_text="",
        backend=FakeBackend(), weights=None,
    )
    assert score.scene_type == "narrative"
    assert score.composite == 50.0


def test_score_scene_raises_on_malformed_json():
    """Unparseable LLM output raises a clear error so the orchestrator can skip the scene."""
    from vlogkit.config import Settings
    from vlogkit.score.scorer import ScoringError, score_scene

    class FakeBackend:
        def complete(self, prompt: str, system: str = "") -> str:
            return "this is not json at all"

    settings = Settings(anthropic_api_key="test-key")
    scenes = [_make_scene_with_context(0)]

    import pytest
    with pytest.raises(ScoringError):
        score_scene(
            scene=scenes[0], scene_index=0, scenes=scenes,
            clip_filename="clip.mp4", transcript_text="",
            backend=FakeBackend(), weights=None,
        )


def test_score_scene_includes_neighbor_descriptions_in_prompt():
    """The prompt must reference the previous and next scene descriptions for context."""
    from vlogkit.config import Settings
    from vlogkit.score.scorer import score_scene

    captured_prompts: list[str] = []

    class FakeBackend:
        def complete(self, prompt: str, system: str = "") -> str:
            captured_prompts.append(prompt)
            return '{"scene_type": "hook", "aesthetic": 50, "credibility": 50, "impact": 50, "memorability": 50, "fun": 50, "rationale": "ok"}'

    scenes = [
        _make_scene_with_context(0, description="opening shot of mountains"),
        _make_scene_with_context(1, description="middle shot of a face"),
        _make_scene_with_context(2, description="closing shot of sky"),
    ]
    settings = Settings(anthropic_api_key="test-key")

    score_scene(
        scene=scenes[1], scene_index=1, scenes=scenes,
        clip_filename="clip.mp4", transcript_text="",
        backend=FakeBackend(), weights=None,
    )
    assert "opening shot of mountains" in captured_prompts[0]
    assert "closing shot of sky" in captured_prompts[0]
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_score.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'vlogkit.score.scorer'`.

- [ ] **Step 3: Create `src/vlogkit/score/scorer.py` with `score_scene()` only**

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_score.py -v
```

Expected: all tests pass (9 weights tests + 4 scorer tests).

- [ ] **Step 5: Commit**

```bash
git add src/vlogkit/score/scorer.py tests/test_score.py
git commit -m "$(cat <<'EOF'
feat(score): add per-scene Murch scoring agent

score_scene() builds a context-rich prompt (description, tags,
transcript, neighbor descriptions), sends it to a Claude backend,
strips any markdown fence, parses strict JSON, and returns a
MurchScore with the composite computed locally from the weight table.
Malformed responses raise ScoringError so the orchestrator can skip.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add `run_scoring()` orchestrator + cache write-back

**Files:**
- Modify: `src/vlogkit/score/scorer.py`
- Modify: `tests/test_score.py`

- [ ] **Step 1: Append the failing tests**

Add to `tests/test_score.py`:

```python
def test_run_scoring_scores_all_unscored_scenes(tmp_path, monkeypatch):
    """run_scoring iterates clips, scores each unscored scene, writes back to cache."""
    from vlogkit.models import ClipAnalysis, ClipMetadata, SceneSegment
    from vlogkit.project import Project
    from vlogkit.score import scorer as scorer_module

    # Set up a fake project with one cached analysis containing two scenes
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

    saved: list[ClipAnalysis] = []
    monkeypatch.setattr(Project, "save_analysis", lambda self, a: saved.append(a))

    score_calls: list[int] = []

    def fake_score_scene(scene, scene_index, **kwargs):
        from vlogkit.models import MurchScore
        score_calls.append(scene_index)
        return MurchScore(
            scene_type="narrative", aesthetic=50, credibility=50, impact=50,
            memorability=50, fun=50, composite=50.0,
        )

    monkeypatch.setattr(scorer_module, "score_scene", fake_score_scene)

    project = Project(tmp_path)
    scored_count = scorer_module.run_scoring(project, force=False)

    assert scored_count == 2
    assert score_calls == [0, 1]
    assert len(saved) == 1
    assert all(s.murch is not None for s in saved[0].scenes)


def test_run_scoring_skips_already_scored_scenes_unless_forced(tmp_path, monkeypatch):
    """By default, scenes with murch already set are skipped. --force re-scores."""
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
    from vlogkit.project import Project
    from vlogkit.score import scorer as scorer_module

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    pre_scored = MurchScore(
        scene_type="hook", aesthetic=80, credibility=80, impact=80,
        memorability=80, fun=80, composite=80.0,
    )
    analysis = ClipAnalysis(
        metadata=ClipMetadata(filename="clip.mp4", path=clip, duration=10.0, resolution=(1, 1), fps=30.0, file_size=4),
        scenes=[SceneSegment(start=0, end=5, murch=pre_scored), SceneSegment(start=5, end=10)],
        file_hash="x",
    )
    monkeypatch.setattr(Project, "scan_clips", lambda self: [clip])
    monkeypatch.setattr(Project, "load_analysis", lambda self, c: analysis)
    monkeypatch.setattr(Project, "save_analysis", lambda self, a: None)

    score_calls: list[int] = []

    def fake_score_scene(scene, scene_index, **kwargs):
        score_calls.append(scene_index)
        return MurchScore(
            scene_type="narrative", aesthetic=50, credibility=50, impact=50,
            memorability=50, fun=50, composite=50.0,
        )

    monkeypatch.setattr(scorer_module, "score_scene", fake_score_scene)

    # Default: skip already-scored
    project = Project(tmp_path)
    scored = scorer_module.run_scoring(project, force=False)
    assert scored == 1
    assert score_calls == [1]  # only the unscored scene

    # --force: re-score everything
    score_calls.clear()
    scored = scorer_module.run_scoring(project, force=True)
    assert scored == 2
    assert score_calls == [0, 1]


def test_run_scoring_continues_when_a_single_scene_fails(tmp_path, monkeypatch, capsys):
    """A ScoringError on one scene logs a warning and continues with the rest."""
    from vlogkit.models import ClipAnalysis, ClipMetadata, MurchScore, SceneSegment
    from vlogkit.project import Project
    from vlogkit.score import scorer as scorer_module
    from vlogkit.score.scorer import ScoringError

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"fake")
    analysis = ClipAnalysis(
        metadata=ClipMetadata(filename="clip.mp4", path=clip, duration=10.0, resolution=(1, 1), fps=30.0, file_size=4),
        scenes=[SceneSegment(start=0, end=5), SceneSegment(start=5, end=10)],
        file_hash="x",
    )
    monkeypatch.setattr(Project, "scan_clips", lambda self: [clip])
    monkeypatch.setattr(Project, "load_analysis", lambda self, c: analysis)
    monkeypatch.setattr(Project, "save_analysis", lambda self, a: None)

    def fake_score_scene(scene, scene_index, **kwargs):
        if scene_index == 0:
            raise ScoringError("simulated parse failure")
        return MurchScore(
            scene_type="narrative", aesthetic=50, credibility=50, impact=50,
            memorability=50, fun=50, composite=50.0,
        )

    monkeypatch.setattr(scorer_module, "score_scene", fake_score_scene)

    project = Project(tmp_path)
    scored = scorer_module.run_scoring(project, force=False)
    assert scored == 1  # only the second scene scored


def test_run_scoring_no_api_key_returns_zero_with_warning(tmp_path, monkeypatch, capsys):
    """Without an API key, scoring is a no-op with a clear warning."""
    from vlogkit.config import Settings
    from vlogkit.project import Project
    from vlogkit.score import scorer as scorer_module

    monkeypatch.setattr(Project, "scan_clips", lambda self: [])

    project = Project(tmp_path, settings=Settings(anthropic_api_key=""))
    scored = scorer_module.run_scoring(project, force=False)
    assert scored == 0
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_score.py -v
```

Expected: FAIL — `run_scoring` doesn't exist yet.

- [ ] **Step 3: Add `run_scoring()` to `src/vlogkit/score/scorer.py`**

Append to the existing `src/vlogkit/score/scorer.py`:

```python
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..llm.claude import ClaudeBackend
from ..models import ClipAnalysis
from ..project import Project
from .weights import load_project_weights

console = Console()


def _transcript_for_scene(analysis: ClipAnalysis, scene_start: float, scene_end: float) -> str:
    """Concatenate transcript segments overlapping the scene's time range."""
    pieces: list[str] = []
    for seg in analysis.transcript:
        if seg.end >= scene_start and seg.start <= scene_end:
            pieces.append(seg.text)
    return " ".join(pieces).strip()


def run_scoring(project: Project, force: bool = False) -> int:
    """Score every detected scene in the project; returns the count of scenes scored.

    Skips scenes whose `murch` is already set unless `force=True`. Skips entirely
    if no API key is configured (prints a warning).
    """
    if not project.settings.anthropic_api_key:
        console.print("[yellow]No API key set; vlogkit score is a no-op. Set VLOGKIT_ANTHROPIC_API_KEY.[/]")
        return 0

    clips = project.scan_clips()
    if not clips:
        console.print("[red]No video clips found.[/]")
        return 0

    backend = ClaudeBackend(project.settings)
    backend.model = project.settings.score_model  # use the dedicated scoring model
    weights = load_project_weights(project.root)

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

            if mutated:
                project.save_analysis(analysis)

    console.print(f"[green]Scored {scored_total} scene(s).[/]")
    return scored_total
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_score.py -v
```

Expected: all tests pass (9 weights + 4 single-scene + 4 orchestrator = 17).

- [ ] **Step 5: Commit**

```bash
git add src/vlogkit/score/scorer.py tests/test_score.py
git commit -m "$(cat <<'EOF'
feat(score): add run_scoring orchestrator with caching

Iterates project clips, scores each unscored scene via score_scene,
writes results back into the existing ClipAnalysis cache. --force
re-scores already-scored scenes. Per-scene failures log a warning and
continue. No API key → no-op with a clear message. Project-local
weight overrides are loaded once per run.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add `score_model` config setting

**Files:**
- Modify: `src/vlogkit/config.py`

- [ ] **Step 1: Verify the existing test pattern**

Look at `src/vlogkit/config.py` — the existing settings are pydantic-settings fields with `VLOGKIT_` env prefix. Adding `score_model` is one line.

- [ ] **Step 2: Add the setting**

In `src/vlogkit/config.py`, locate the existing `claude_vision_model` field and add `score_model` immediately after it:

```python
    claude_vision_model: str = "claude-sonnet-4-20250514"
    score_model: str = "claude-sonnet-4-20250514"  # VLOGKIT_SCORE_MODEL
```

- [ ] **Step 3: Confirm import + default work**

```bash
PYTHONPATH=src .venv/bin/python -c "from vlogkit.config import Settings; print(Settings().score_model)"
```

Expected: prints `claude-sonnet-4-20250514` (or whatever the default is — should match `claude_model`).

- [ ] **Step 4: Commit**

```bash
git add src/vlogkit/config.py
git commit -m "$(cat <<'EOF'
feat(config): add score_model setting

VLOGKIT_SCORE_MODEL configures the Claude model used for Murch scoring.
Defaults to the same Sonnet model as claude_model.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Add the `vlogkit score` CLI command

**Files:**
- Modify: `src/vlogkit/cli.py`
- Modify: `tests/test_score.py`

- [ ] **Step 1: Append the failing test**

Add to `tests/test_score.py`:

```python
def test_cli_score_command_invokes_run_scoring(tmp_path, monkeypatch):
    """`vlogkit score` reaches run_scoring with the right project and force flag."""
    from typer.testing import CliRunner

    from vlogkit.cli import app

    captured: dict[str, object] = {}

    def fake_run_scoring(project, force=False):
        captured["force"] = force
        captured["project_root"] = project.root
        return 0

    monkeypatch.setattr("vlogkit.score.scorer.run_scoring", fake_run_scoring)

    runner = CliRunner()
    result = runner.invoke(app, ["score", "-p", str(tmp_path), "--force"])
    assert result.exit_code == 0, result.output
    assert captured["force"] is True
    assert str(captured["project_root"]) == str(tmp_path.resolve())


def test_cli_score_command_default_force_false(tmp_path, monkeypatch):
    """Without --force, run_scoring is called with force=False."""
    from typer.testing import CliRunner

    from vlogkit.cli import app

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "vlogkit.score.scorer.run_scoring",
        lambda project, force=False: captured.setdefault("force", force) or 0,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["score", "-p", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert captured["force"] is False
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_score.py::test_cli_score_command_invokes_run_scoring tests/test_score.py::test_cli_score_command_default_force_false -v
```

Expected: FAIL with "No such command 'score'".

- [ ] **Step 3: Add the `score` command to `src/vlogkit/cli.py`**

Find a good insertion point (right after the `analyze` command makes sense narratively). Add:

```python
@app.command()
def score(
    path: Annotated[Optional[Path], typer.Option("--path", "-p", help="Project directory")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Re-score scenes that already have a Murch score")] = False,
):
    """Score every detected scene with Murch-style 5-dim weighted ratings."""
    project = _get_project(path)
    if not project.is_initialized():
        console.print("[red]Not a vlogkit project. Run `vlogkit init` first.[/]")
        raise typer.Exit(1)

    from .score.scorer import run_scoring

    run_scoring(project, force=force)
```

The imports at the top of `cli.py` already cover `typer`, `Annotated`, `Optional`, `Path`, and `console` — no new imports needed.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests/test_score.py -v
```

Expected: all 19 tests pass (17 score + 2 CLI).

- [ ] **Step 5: Commit**

```bash
git add src/vlogkit/cli.py tests/test_score.py
git commit -m "$(cat <<'EOF'
feat(cli): add `vlogkit score` command

New CLI command runs Murch-style 5-dim weighted scoring over every
detected scene. --force re-scores scenes that already have a score;
default skips already-scored scenes for cheap incremental runs.

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
PYTHONPATH=src .venv/bin/python -m pytest -v 2>&1 | tail -40
```

Expected: all the new score tests pass; pre-existing PR-1-baseline failures (`tests/test_search.py::*`, `tests/server/test_ws.py::*`, `tests/server/test_openapi_snapshot.py`) are unchanged. No NEW failures.

- [ ] **Step 2: If a new regression is found, fix it inline**

Most likely failure: a model test that round-trips a `SceneSegment` snapshot from before this PR could fail if the snapshot doesn't include `murch: null`. Check `tests/test_models.py` for any frozen JSON. Pydantic should accept the missing key as `None` — but if any test compares `model_dump()` output to a fixed dict, the output dict will now include `"murch": None` and the comparison will fail. Add `"murch": None` to the expected dict in those tests.

- [ ] **Step 3: Commit (if any fixes were needed)**

```bash
git add tests/
git commit -m "$(cat <<'EOF'
test(models): add murch=None to expected serialized SceneSegment fixtures

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If no fixes needed, skip this commit.

---

## Task 9: Manual smoke test

These tasks require either real video or human judgment — do not delegate to a subagent.

- [ ] **Step 1: Reuse the smoke project from Plan 1, or generate a new one**

If `/tmp/vlogkit-smoke-*` from Plan 1 still exists, use it. Otherwise:

```bash
SMOKE=/tmp/vlogkit-smoke-plan2-$(date +%s)
mkdir -p "$SMOKE"
ffmpeg -y -f lavfi -i "color=c=red:s=320x240:d=4,format=yuv420p" \
        -f lavfi -i "color=c=green:s=320x240:d=4,format=yuv420p" \
        -f lavfi -i "color=c=blue:s=320x240:d=4,format=yuv420p" \
        -filter_complex "[0:v][1:v][2:v]concat=n=3:v=1[v]" \
        -map "[v]" -c:v libx264 -pix_fmt yuv420p -t 12 \
        "$SMOKE/test_clip.mp4"
echo "$SMOKE" > /tmp/vlogkit-smoke-plan2.txt
```

- [ ] **Step 2: Run analyze (with vision off, since the synthetic clip has no real content)**

```bash
SMOKE=$(cat /tmp/vlogkit-smoke-plan2.txt)
cd "$SMOKE"
VLOGKIT_SEARCH_AUTO_INDEX=false PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src \
  /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -c "from vlogkit.cli import app; app()" init .
VLOGKIT_SEARCH_AUTO_INDEX=false PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src \
  /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -c "from vlogkit.cli import app; app()" analyze --no-vision --force
```

Expected: 3 scenes detected, descriptions empty.

- [ ] **Step 3: Run score (will silently no-op since no API key, OR score for real if API key set)**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src \
  /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -c "from vlogkit.cli import app; app()" score
```

Expected (no API key): yellow warning "No API key set; vlogkit score is a no-op."
Expected (with API key): per-scene progress messages, final "Scored N scene(s)."

- [ ] **Step 4: If API key was set, inspect the cache JSON**

```bash
PY=/Users/bryan/Code/lsl/vlogkit/.venv/bin/python
$PY -c "
import json
from pathlib import Path
for f in Path('.vlogkit/clips').glob('*.json'):
    data = json.loads(f.read_text())
    for i, s in enumerate(data['scenes']):
        m = s.get('murch')
        if m:
            print(f'    scene {i}: {m[\"scene_type\"]:10s} composite={m[\"composite\"]:.1f}  ({m.get(\"rationale\", \"\")})')
        else:
            print(f'    scene {i}: (no score)')
"
```

Expected: each scene shows a scene_type, composite score, and rationale.

- [ ] **Step 5: Re-run score without --force (should be no-op)**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src \
  /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -c "from vlogkit.cli import app; app()" score
```

Expected: "Scored 0 scene(s)." (since all are already scored).

- [ ] **Step 6: Re-run with --force (should re-score all)**

```bash
PYTHONPATH=/Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1/src \
  /Users/bryan/Code/lsl/vlogkit/.venv/bin/python -c "from vlogkit.cli import app; app()" score --force
```

Expected: "Scored 3 scene(s)." (all re-scored).

---

## Task 10: Open the PR

- [ ] **Step 1: Push the branch**

```bash
cd /Users/bryan/Code/lsl/vlogkit/.claude/worktrees/loving-chatterjee-4a0ad1
git push -u origin claude/plan-2-scoring
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "feat(score): add vlogkit score command + Murch scoring (PR 2 of 3)" --body "$(cat <<'EOF'
## Summary
- New `vlogkit score` CLI command that grades every detected scene on five Murch-style dimensions (aesthetic, credibility, impact, memorability, fun) with scene-type-aware weighted composites.
- New `score/` package: `weights.py` (default + project-local override loading), `prompts.py` (the scoring prompt), `scorer.py` (single-scene + orchestrator).
- New `MurchScore` Pydantic model + optional `SceneSegment.murch` field. Backward-compatible: old cache files without `murch` load cleanly.
- New `score_model` config setting (defaults to the Sonnet baseline).
- Scoring is opt-in: `vlogkit score` is a separate command between `analyze` and `storyboard`.

This is **PR 2 of 3**. PR 3 will refactor storyboard generation into a Director→Editor→Polisher pipeline that consumes these scores.

## Test plan
- [x] 19 new unit tests in `tests/test_score.py` cover: weight tables, composite calculation, project-local overrides (full + partial + malformed), scene-scoring agent (valid response + markdown fence + malformed JSON + neighbor context), orchestrator (--force vs default + per-scene-failure isolation + no-API-key path), CLI flag threading
- [x] Backward-compat tests in `tests/test_models.py`: old cache JSON without `murch` key loads with `murch=None`
- [x] Manual smoke test against synthetic 3-scene ffmpeg clip
- [x] No regressions in pre-existing test suite (Plan 1's known unrelated failures are unchanged)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Capture the PR URL** for use in Plan 3.

---

## Self-review checklist (do before declaring Plan 2 done)

- [ ] Every step has actual code / commands, no placeholders
- [ ] `MurchScore` schema is consistent across model definition, prompt expectations, and parser
- [ ] `score_scene` signature matches every test invocation
- [ ] `run_scoring` signature: `(project, force=False) -> int`
- [ ] CLI command name is `score` (not `scoring` or `score-scenes`)
- [ ] All 19 score tests + 5 model tests reference symbols defined in the preceding tasks
- [ ] Plan covers spec §4 (Murch scoring), §6.1 (models), §6.2 (config), §6.3 (CLI), §8 PR 2
- [ ] Commits are small and each focused on one logical change
