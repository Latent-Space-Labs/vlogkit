"""Tests for the TightenConfig model (auto-cut contract)."""

from vlogkit.models import TightenConfig


def test_tighten_config_defaults():
    cfg = TightenConfig()
    assert cfg.remove_silence is True
    assert cfg.remove_fillers is True
    assert cfg.min_silence > 0
    assert cfg.pad >= 0
    assert cfg.min_keep > 0
    # Default filler lexicon is the SAFE, unambiguous set (no real words like "so"/"like").
    assert "um" in cfg.fillers
    assert "uh" in cfg.fillers
    assert "so" not in cfg.fillers
    assert "like" not in cfg.fillers


def test_tighten_config_roundtrip():
    cfg = TightenConfig(min_silence=1.0, fillers=["um", "yeah"])
    assert TightenConfig.model_validate_json(cfg.model_dump_json()) == cfg
