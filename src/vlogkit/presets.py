"""Named content presets that bundle storyboard/caption/tighten/score tunables.

A preset is a small recipe that writes the project-local config files the rest
of the pipeline already reads:

  - `.vlogkit/caption_style.json`  (merged over CaptionStyle defaults)
  - `.vlogkit/tighten.json`        (merged over TightenConfig defaults)
  - `.vlogkit/score_weights.json`  (merged over DEFAULT_WEIGHTS, optional)

The storyboard `strategy` string is carried on the Preset for the CLI to pass
to `vlogkit storyboard -s ...`; `apply_preset` does not run the storyboard.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # avoid import cycle / heavy import at module load
    from .project import Project


class Preset(BaseModel):
    """A named bundle of pipeline tunables."""

    name: str
    description: str
    strategy: str  # storyboard strategy: chronological | energy-arc | thematic
    caption_style: dict = Field(default_factory=dict)  # partial caption_style.json
    tighten: dict = Field(default_factory=dict)  # partial tighten.json
    score_weights: dict | None = None  # partial score_weights.json; None = leave defaults


PRESETS: dict[str, Preset] = {
    "tutorial": Preset(
        name="tutorial",
        description=(
            "Clear, instructional edit: thematic ordering, readable static "
            "captions, and aggressive silence/filler removal so explanations "
            "stay tight. Scoring rewards credible, on-message narrative clips."
        ),
        strategy="thematic",
        caption_style={
            "font_size": 56,
            "primary_color": "#FFFFFF",
            "highlight_color": "#FFE000",
            "position": "bottom",
            "karaoke": False,
            "animation": "none",
            "max_chars_per_line": 38,
        },
        tighten={
            "remove_silence": True,
            "remove_fillers": True,
            "min_silence": 0.5,
            "pad": 0.08,
            "min_keep": 0.3,
        },
        score_weights={
            # Favor credibility / clarity in the explanatory narrative clips.
            "narrative": {
                "aesthetic": 0.10,
                "credibility": 0.45,
                "impact": 0.20,
                "memorability": 0.15,
                "fun": 0.10,
            },
        },
    ),
    "vlog": Preset(
        name="vlog",
        description=(
            "Personality-driven social edit: energy-arc pacing, punchy "
            "karaoke pop captions, and moderate tightening. Scoring leans into "
            "fun and impact on the opening hook."
        ),
        strategy="energy-arc",
        caption_style={
            "font_size": 52,
            "primary_color": "#FFFFFF",
            "highlight_color": "#00E0FF",
            "position": "bottom",
            "karaoke": True,
            "animation": "pop",
            "max_chars_per_line": 32,
        },
        tighten={
            "remove_silence": True,
            "remove_fillers": True,
            "min_silence": 0.8,
            "pad": 0.12,
            "min_keep": 0.3,
        },
        score_weights={
            # Hooks should be fun and high-impact to grab attention fast.
            "hook": {
                "aesthetic": 0.10,
                "credibility": 0.05,
                "impact": 0.35,
                "memorability": 0.20,
                "fun": 0.30,
            },
        },
    ),
    "travel": Preset(
        name="travel",
        description=(
            "Cinematic montage edit: energy-arc pacing, centered highlight-box "
            "captions, and light tightening that keeps natural pauses and "
            "ambience. Scoring strongly favors aesthetic clips."
        ),
        strategy="energy-arc",
        caption_style={
            "font_size": 50,
            "primary_color": "#FFFFFF",
            "highlight_color": "#FFD27F",
            "position": "center",
            "karaoke": False,
            "animation": "highlight_box",
            "max_chars_per_line": 36,
        },
        tighten={
            # Light touch: trim fillers but keep silences/ambience intact.
            "remove_silence": False,
            "remove_fillers": True,
            "min_silence": 1.0,
            "pad": 0.15,
            "min_keep": 0.4,
        },
        score_weights={
            # Beauty over talk: boost aesthetic across the cinematic scene types.
            "aesthetic": {
                "aesthetic": 0.60,
                "credibility": 0.05,
                "impact": 0.15,
                "memorability": 0.15,
                "fun": 0.05,
            },
            "hook": {
                "aesthetic": 0.40,
                "credibility": 0.05,
                "impact": 0.25,
                "memorability": 0.20,
                "fun": 0.10,
            },
        },
    ),
}


def list_presets() -> list[Preset]:
    """Return all registered presets."""
    return list(PRESETS.values())


def get_preset(name: str) -> Preset:
    """Look up a preset by name. Raises KeyError if unknown."""
    try:
        return PRESETS[name]
    except KeyError:
        raise KeyError(
            f"Unknown preset {name!r}. Available: {', '.join(sorted(PRESETS))}"
        ) from None


def apply_preset(project: "Project", name: str) -> Preset:
    """Write a preset's config files into the project's `.vlogkit/` directory.

    Writes caption_style.json and tighten.json always, and score_weights.json
    only when the preset specifies weights. Each managed file is fully replaced;
    the respective loaders merge the partial dicts over their defaults. Returns
    the applied Preset (its `strategy` is for the caller to feed to storyboard).
    """
    preset = get_preset(name)
    cache_dir = project.cache_dir

    (cache_dir / "caption_style.json").write_text(
        json.dumps(preset.caption_style, indent=2)
    )
    (cache_dir / "tighten.json").write_text(json.dumps(preset.tighten, indent=2))
    if preset.score_weights is not None:
        (cache_dir / "score_weights.json").write_text(
            json.dumps(preset.score_weights, indent=2)
        )

    return preset
