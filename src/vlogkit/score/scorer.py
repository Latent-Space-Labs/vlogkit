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
