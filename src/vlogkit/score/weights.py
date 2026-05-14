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
