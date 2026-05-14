"""Build a storyboard via the Director → Editor → Polisher multi-agent pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from rich.console import Console

from ..config import Settings
from ..llm.claude import ClaudeBackend
from ..models import ClipAnalysis, Storyboard
from .agents import director, editor, polisher
from .agents.base import AgentError
from .strategies import chronological_fallback

console = Console()

EventCallback = Callable[..., None]


def build_storyboard(
    analyses: list[ClipAnalysis],
    project_root: Path,
    settings: Settings,
    strategy: str = "energy-arc",
    context: str = "a recent trip",
    event_callback: EventCallback | None = None,
) -> Storyboard:
    """Generate a storyboard via the multi-agent pipeline.

    No API key → chronological fallback (no LLM, no events).
    Any agent failure → chronological fallback with a warning naming the stage.

    event_callback (when provided) is invoked with:
      - ("agent_started", stage)
      - ("agent_complete", stage, summary)
      - ("agent_failed", stage, reason)
    """
    if not settings.anthropic_api_key:
        console.print("[yellow]No API key found. Using chronological fallback.[/]")
        return chronological_fallback(analyses)

    backend = ClaudeBackend(settings)
    backend.model = settings.storyboard_model

    def emit(event_type: str, stage: str, summary_or_reason: str = "") -> None:
        if event_callback is not None:
            event_callback(event_type, stage, summary_or_reason)

    try:
        console.print("[cyan]Director: planning narrative arc...[/]")
        emit("agent_started", "director")
        plan = director.run(
            analyses=analyses, strategy=strategy, context=context, backend=backend,
        )
        emit("agent_complete", "director", f"Planned {len(plan.sections)} sections")

        console.print("[cyan]Editor: selecting scenes...[/]")
        emit("agent_started", "editor")
        assignments = editor.run(plan=plan, analyses=analyses, backend=backend)
        n_picks = sum(len(a.picks) for a in assignments.assignments)
        emit("agent_complete", "editor", f"Picked {n_picks} segments")

        console.print("[cyan]Polisher: finalizing transitions and labels...[/]")
        emit("agent_started", "polisher")
        storyboard = polisher.run(
            plan=plan, assignments=assignments, analyses=analyses,
            project_root=project_root, backend=backend,
        )
        emit("agent_complete", "polisher", "Storyboard ready")

        console.print(
            f"[green]Storyboard created: {len(storyboard.sections)} section(s).[/]"
        )
        return storyboard

    except AgentError as e:
        emit("agent_failed", e.stage, e.reason)
        console.print(
            f"[yellow]Multi-agent flow failed at stage '{e.stage}': {e.reason}. "
            f"Falling back to chronological order.[/]"
        )
        return chronological_fallback(analyses)
