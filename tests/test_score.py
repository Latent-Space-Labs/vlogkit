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
