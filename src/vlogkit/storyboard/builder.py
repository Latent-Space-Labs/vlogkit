"""Build a storyboard from clip analyses via LLM."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

from ..config import Settings
from ..llm.base import LLMBackend
from ..llm.claude import ClaudeBackend
from ..models import ClipAnalysis, Storyboard, StoryboardSection, StoryboardSegment
from ..templates import get_template, template_to_prompt_hint
from .prompts import (
    DURATION_INSTRUCTION,
    STORYBOARD_PROMPT,
    STRATEGY_HINTS,
    SYSTEM_PROMPT,
    TEMPLATE_INSTRUCTION,
)
from .strategies import chronological_fallback

console = Console()


def _clips_to_json(analyses: list[ClipAnalysis]) -> str:
    clips = []
    for a in analyses:
        transcript_text = " ".join(seg.text for seg in a.transcript)
        clips.append({
            "filename": a.metadata.filename,
            "duration": a.metadata.duration,
            "resolution": list(a.metadata.resolution),
            "fps": a.metadata.fps,
            "creation_time": a.metadata.creation_time.isoformat() if a.metadata.creation_time else None,
            "transcript": transcript_text[:500] if transcript_text else "(no speech)",
            "summary": a.summary,
        })
    return json.dumps(clips, indent=2)


def _parse_storyboard_response(raw: str, project_root: Path) -> Storyboard:
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    data = json.loads(text)

    sections = []
    for sec_data in data.get("sections", []):
        segments = []
        for seg_data in sec_data.get("segments", []):
            clip_name = seg_data["clip_path"]
            # Resolve to full path
            clip_path = project_root / clip_name
            if not clip_path.exists():
                # Try to find it
                matches = list(project_root.rglob(clip_name))
                clip_path = matches[0] if matches else Path(clip_name)

            segments.append(StoryboardSegment(
                clip_path=clip_path,
                in_point=float(seg_data.get("in_point", 0)),
                out_point=float(seg_data.get("out_point", 0)),
                label=seg_data.get("label", ""),
                transition=seg_data.get("transition", "cut"),
                include=seg_data.get("include", True),
            ))
        sections.append(StoryboardSection(
            title=sec_data.get("title", "Untitled"),
            segments=segments,
            notes=sec_data.get("notes", ""),
        ))

    return Storyboard(
        title=data.get("title", "Untitled Vlog"),
        sections=sections,
        total_duration=float(data.get("total_duration", 0)),
        llm_rationale=data.get("llm_rationale", ""),
    )


def build_storyboard(
    analyses: list[ClipAnalysis],
    project_root: Path,
    settings: Settings,
    strategy: str = "energy-arc",
    context: str = "a recent trip",
    target_duration: float | None = None,
    template_name: str | None = None,
) -> Storyboard:
    if not settings.anthropic_api_key:
        console.print("[yellow]No API key found. Using chronological fallback.[/]")
        return chronological_fallback(analyses, target_duration=target_duration)

    backend: LLMBackend = ClaudeBackend(settings)
    clips_json = _clips_to_json(analyses)

    # Build duration block
    duration_block = ""
    if target_duration is not None:
        duration_block = DURATION_INSTRUCTION.format(target_duration=target_duration)

    # Build template block
    template_block = ""
    if template_name:
        tmpl = get_template(template_name)
        hint = template_to_prompt_hint(tmpl, target_duration or 60.0)
        template_block = TEMPLATE_INSTRUCTION.format(template_hint=hint)
        strategy_hint = "See template structure above for section guidance."
    else:
        strategy_hint = STRATEGY_HINTS.get(strategy, STRATEGY_HINTS["energy-arc"])

    prompt = STORYBOARD_PROMPT.format(
        clip_count=len(analyses),
        context=context,
        strategy=strategy_hint,
        clips_json=clips_json,
        duration_block=duration_block,
        template_block=template_block,
    )

    console.print("[cyan]Generating storyboard via Claude...[/]")
    response = backend.complete(prompt, system=SYSTEM_PROMPT)

    try:
        storyboard = _parse_storyboard_response(response, project_root)
        storyboard.target_duration = target_duration
        storyboard.template_name = template_name
        console.print(f"[green]Storyboard created: {len(storyboard.sections)} sections[/]")
        if target_duration:
            actual = storyboard.included_duration()
            console.print(f"Target: {target_duration:.0f}s | Actual: {actual:.0f}s")
        return storyboard
    except (json.JSONDecodeError, KeyError) as e:
        console.print(f"[red]Failed to parse LLM response: {e}[/]")
        console.print("[yellow]Falling back to chronological order.[/]")
        return chronological_fallback(analyses, target_duration=target_duration)
