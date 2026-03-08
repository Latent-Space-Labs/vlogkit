"""Vlog formula templates — reusable editing presets."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class TemplateSectionSpec(BaseModel):
    name: str
    duration_pct: float
    description: str
    pacing: str = "medium"
    transition_hint: str = "cut"


class VlogTemplate(BaseModel):
    name: str
    description: str
    sections: list[TemplateSectionSpec] = Field(default_factory=list)
    editing_style: str = ""
    builtin: bool = True


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

BUILTIN_TEMPLATES: dict[str, VlogTemplate] = {
    "hook-highlights-cta": VlogTemplate(
        name="hook-highlights-cta",
        description="Attention-grabbing opener, best moments montage, closing CTA",
        editing_style="Fast-paced montage with jump cuts and energy",
        sections=[
            TemplateSectionSpec(
                name="Hook",
                duration_pct=0.08,
                description="Attention-grabbing opener — the single best or most surprising moment",
                pacing="fast",
                transition_hint="cut",
            ),
            TemplateSectionSpec(
                name="Highlights",
                duration_pct=0.80,
                description="Best moments montage — varied clips showing the best of the day",
                pacing="fast",
                transition_hint="cut",
            ),
            TemplateSectionSpec(
                name="CTA",
                duration_pct=0.12,
                description="Closing moment — wrap up, call to action, or memorable final shot",
                pacing="medium",
                transition_hint="fade",
            ),
        ],
    ),
    "day-diary": VlogTemplate(
        name="day-diary",
        description="Chronological morning-to-night day-in-the-life diary",
        editing_style="Natural chronological flow, relaxed pacing with occasional quick cuts",
        sections=[
            TemplateSectionSpec(
                name="Morning",
                duration_pct=0.20,
                description="Start of day — waking up, breakfast, getting ready",
                pacing="slow",
                transition_hint="dissolve",
            ),
            TemplateSectionSpec(
                name="Midday",
                duration_pct=0.25,
                description="Middle of day activities — work, errands, main event",
                pacing="medium",
                transition_hint="cut",
            ),
            TemplateSectionSpec(
                name="Afternoon",
                duration_pct=0.30,
                description="Afternoon activities — the peak of the day",
                pacing="medium",
                transition_hint="cut",
            ),
            TemplateSectionSpec(
                name="Evening",
                duration_pct=0.25,
                description="Wind down — dinner, reflection, end of day",
                pacing="slow",
                transition_hint="dissolve",
            ),
        ],
    ),
    "topic-montage": VlogTemplate(
        name="topic-montage",
        description="Auto-detect themes and group clips by topic with equal time per group",
        editing_style="Thematic grouping — each topic gets its own mini-section with transitions between",
        sections=[
            TemplateSectionSpec(
                name="Auto-detect themes",
                duration_pct=1.0,
                description=(
                    "Identify 2-4 distinct themes/topics/activities across all clips. "
                    "Create one section per theme. Divide time equally between themes. "
                    "Pick the best clips for each theme and trim to fit."
                ),
                pacing="medium",
                transition_hint="dissolve",
            ),
        ],
    ),
}


# ---------------------------------------------------------------------------
# Template loading / saving
# ---------------------------------------------------------------------------

_USER_TEMPLATES_DIR = Path.home() / ".vlogkit" / "templates"


def get_builtin_templates() -> dict[str, VlogTemplate]:
    return dict(BUILTIN_TEMPLATES)


def load_user_templates() -> dict[str, VlogTemplate]:
    templates: dict[str, VlogTemplate] = {}
    if not _USER_TEMPLATES_DIR.exists():
        return templates

    for p in sorted(_USER_TEMPLATES_DIR.iterdir()):
        if p.suffix not in (".json", ".yaml", ".yml"):
            continue
        try:
            if p.suffix == ".json":
                data = json.loads(p.read_text())
            else:
                # YAML support — optional dependency
                try:
                    import yaml  # type: ignore[import-untyped]

                    data = yaml.safe_load(p.read_text())
                except ImportError:
                    continue
            tmpl = VlogTemplate.model_validate(data)
            tmpl.builtin = False
            templates[tmpl.name] = tmpl
        except Exception:
            continue
    return templates


def get_all_templates() -> dict[str, VlogTemplate]:
    all_t = get_builtin_templates()
    all_t.update(load_user_templates())  # user templates override builtins
    return all_t


def get_template(name: str) -> VlogTemplate:
    all_t = get_all_templates()
    if name not in all_t:
        available = ", ".join(sorted(all_t.keys()))
        raise ValueError(f"Unknown template '{name}'. Available: {available}")
    return all_t[name]


def save_template(template: VlogTemplate) -> Path:
    _USER_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    out = _USER_TEMPLATES_DIR / f"{template.name}.json"
    template.builtin = False
    out.write_text(template.model_dump_json(indent=2))
    return out


# ---------------------------------------------------------------------------
# Convert template to LLM prompt hint
# ---------------------------------------------------------------------------


def template_to_prompt_hint(template: VlogTemplate, target_duration: float) -> str:
    lines = []
    cumulative = 0.0
    for i, sec in enumerate(template.sections, 1):
        sec_seconds = sec.duration_pct * target_duration
        start = cumulative
        end = cumulative + sec_seconds
        cumulative = end
        lines.append(
            f'{i}. "{sec.name}" ({start:.0f}s-{end:.0f}s, ~{sec.duration_pct * 100:.0f}%): '
            f"{sec.description}. Pacing: {sec.pacing}. Transition: {sec.transition_hint}"
        )

    section_specs = "\n".join(lines)
    result = f"Structure this vlog into exactly these sections:\n{section_specs}"
    if template.editing_style:
        result += f"\n\nEditing style: {template.editing_style}"
    return result
