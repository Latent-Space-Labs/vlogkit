"""Tests for content presets (vlogkit.presets)."""

from __future__ import annotations

import json

import pytest

from vlogkit.models import CaptionStyle, TightenConfig
from vlogkit.presets import (
    PRESETS,
    Preset,
    apply_preset,
    get_preset,
    list_presets,
)
from vlogkit.project import Project

VALID_STRATEGIES = {"chronological", "energy-arc", "thematic"}


def test_list_presets_returns_at_least_three():
    presets = list_presets()
    assert len(presets) >= 3
    assert all(isinstance(p, Preset) for p in presets)


def test_expected_presets_present():
    names = {p.name for p in list_presets()}
    assert {"tutorial", "vlog", "travel"} <= names


def test_get_preset_known():
    p = get_preset("tutorial")
    assert isinstance(p, Preset)
    assert p.name == "tutorial"


def test_get_preset_unknown_raises():
    with pytest.raises((KeyError, ValueError)):
        get_preset("does-not-exist")


def test_preset_strategies_are_valid():
    for p in list_presets():
        assert p.strategy in VALID_STRATEGIES


def test_presets_are_distinct():
    presets = list_presets()
    strategies = {p.name: p.strategy for p in presets}
    # tutorial uses thematic; others use energy-arc — at least two distinct strategies
    assert len({p.strategy for p in presets}) >= 2
    # caption_style dicts should not be identical across the three named presets
    styles = [
        json.dumps(get_preset(n).caption_style, sort_keys=True)
        for n in ("tutorial", "vlog", "travel")
    ]
    assert len(set(styles)) == 3
    assert strategies["tutorial"] == "thematic"


def test_preset_caption_style_valid_against_model():
    for p in list_presets():
        merged = {**CaptionStyle().model_dump(), **p.caption_style}
        # Must not raise
        CaptionStyle.model_validate(merged)


def test_preset_tighten_valid_against_model():
    for p in list_presets():
        merged = {**TightenConfig().model_dump(), **p.tighten}
        TightenConfig.model_validate(merged)


def test_preset_score_weights_shape():
    for p in list_presets():
        if p.score_weights is None:
            continue
        for scene_type, dims in p.score_weights.items():
            assert scene_type in {"hook", "narrative", "aesthetic", "commercial"}
            assert isinstance(dims, dict)
            for dim in dims:
                assert dim in {"aesthetic", "credibility", "impact", "memorability", "fun"}


def test_apply_preset_writes_files(tmp_path):
    project = Project(tmp_path)
    project.init()

    preset = apply_preset(project, "tutorial")
    assert isinstance(preset, Preset)
    assert preset.name == "tutorial"

    cap_path = project.cache_dir / "caption_style.json"
    tighten_path = project.cache_dir / "tighten.json"

    assert cap_path.exists()
    assert tighten_path.exists()

    assert json.loads(cap_path.read_text()) == preset.caption_style
    assert json.loads(tighten_path.read_text()) == preset.tighten

    weights_path = project.cache_dir / "score_weights.json"
    if preset.score_weights is not None:
        assert weights_path.exists()
        assert json.loads(weights_path.read_text()) == preset.score_weights


def test_apply_preset_skips_score_weights_when_none(tmp_path):
    project = Project(tmp_path)
    project.init()

    # Find a preset with score_weights=None if any; otherwise simulate via registry.
    none_presets = [p for p in list_presets() if p.score_weights is None]
    if not none_presets:
        pytest.skip("no preset with score_weights=None")
    apply_preset(project, none_presets[0].name)
    assert not (project.cache_dir / "score_weights.json").exists()


def test_apply_preset_unknown_raises(tmp_path):
    project = Project(tmp_path)
    project.init()
    with pytest.raises((KeyError, ValueError)):
        apply_preset(project, "nope")


def test_applied_files_load_through_real_loaders(tmp_path):
    from vlogkit.captions.pipeline import load_caption_style
    from vlogkit.edit.tighten import load_tighten_config
    from vlogkit.score.weights import load_project_weights

    project = Project(tmp_path)
    project.init()
    preset = apply_preset(project, "vlog")

    style = load_caption_style(project.root)
    assert isinstance(style, CaptionStyle)

    tighten = load_tighten_config(project.root)
    assert isinstance(tighten, TightenConfig)

    weights = load_project_weights(project.root)
    assert set(weights.keys()) == {"hook", "narrative", "aesthetic", "commercial"}
    if preset.score_weights:
        for scene_type, dims in preset.score_weights.items():
            for dim, val in dims.items():
                assert weights[scene_type][dim] == val
