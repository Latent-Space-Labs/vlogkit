"""Build a storyboard via the Director → Editor → Polisher multi-agent pipeline."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from ..config import Settings
from ..llm.claude import ClaudeBackend
from ..models import ClipAnalysis, Storyboard
from .agents import director, editor, polisher
from .agents.base import AgentError
from .strategies import chronological_fallback

console = Console()


def build_storyboard(
    analyses: list[ClipAnalysis],
    project_root: Path,
    settings: Settings,
    strategy: str = "energy-arc",
    context: str = "a recent trip",
) -> Storyboard:
    """Generate a storyboard via the multi-agent pipeline.

    No API key → chronological fallback (no LLM).
    Any agent failure → chronological fallback with a warning naming the stage.
    """
    if not settings.anthropic_api_key:
        console.print("[yellow]No API key found. Using chronological fallback.[/]")
        return chronological_fallback(analyses)

    backend = ClaudeBackend(settings)
    backend.model = settings.storyboard_model

    try:
        console.print("[cyan]Director: planning narrative arc...[/]")
        plan = director.run(
            analyses=analyses, strategy=strategy, context=context, backend=backend,
        )

        console.print("[cyan]Editor: selecting scenes...[/]")
        assignments = editor.run(plan=plan, analyses=analyses, backend=backend)

        console.print("[cyan]Polisher: finalizing transitions and labels...[/]")
        storyboard = polisher.run(
            plan=plan, assignments=assignments, analyses=analyses,
            project_root=project_root, backend=backend,
        )

        console.print(
            f"[green]Storyboard created: {len(storyboard.sections)} section(s).[/]"
        )
        return storyboard

    except AgentError as e:
        console.print(
            f"[yellow]Multi-agent flow failed at stage '{e.stage}': {e.reason}. "
            f"Falling back to chronological order.[/]"
        )
        return chronological_fallback(analyses)
