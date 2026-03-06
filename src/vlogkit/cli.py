"""vlogkit CLI — Typer application."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import get_settings
from .project import Project

app = typer.Typer(
    name="vlogkit",
    help="AI-powered vlog assembly tool",
    no_args_is_help=True,
)
console = Console()


def _get_project(path: Path | None = None) -> Project:
    root = path or Path.cwd()
    return Project(root.resolve())


@app.command()
def init(
    path: Annotated[Optional[Path], typer.Argument(help="Project directory")] = None,
):
    """Initialize a vlogkit project — scan for video clips."""
    project = _get_project(path)
    clips = project.init()
    console.print(f"[green]Initialized vlogkit project at {project.root}[/]")
    console.print(f"Found [bold]{len(clips)}[/] video clips:")
    for c in clips:
        console.print(f"  {c.name}")


@app.command()
def analyze(
    path: Annotated[Optional[Path], typer.Option("--path", "-p", help="Project directory")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Re-analyze all clips")] = False,
):
    """Run analysis pipeline (transcribe, extract metadata). Results are cached."""
    project = _get_project(path)
    if not project.is_initialized():
        console.print("[red]Not a vlogkit project. Run `vlogkit init` first.[/]")
        raise typer.Exit(1)

    from .analyze.pipeline import run_analysis

    run_analysis(project, force=force)


@app.command()
def storyboard(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
    strategy: Annotated[str, typer.Option("--strategy", "-s", help="chronological|energy-arc|thematic")] = "energy-arc",
    context: Annotated[str, typer.Option("--context", "-c", help="Brief description of the clips")] = "a recent trip",
):
    """Generate an AI storyboard from analyzed clips."""
    project = _get_project(path)
    if not project.is_initialized():
        console.print("[red]Not a vlogkit project. Run `vlogkit init` first.[/]")
        raise typer.Exit(1)

    analyses = project.load_all_analyses()
    if not analyses:
        console.print("[red]No analyses found. Run `vlogkit analyze` first.[/]")
        raise typer.Exit(1)

    from .storyboard.builder import build_storyboard
    from .interactive.markdown import storyboard_to_markdown

    sb = build_storyboard(analyses, project.root, project.settings, strategy=strategy, context=context)
    project.save_storyboard(sb)

    md = storyboard_to_markdown(sb)
    project.storyboard_path().write_text(md)
    console.print(f"[green]Storyboard saved to {project.storyboard_path()}[/]")
    console.print(f"Sections: {len(sb.sections)} | Included duration: {sb.included_duration():.0f}s")


@app.command()
def review(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
):
    """Open storyboard.md in $EDITOR for review and editing."""
    project = _get_project(path)
    sb_path = project.storyboard_path()
    if not sb_path.exists():
        console.print("[red]No storyboard found. Run `vlogkit storyboard` first.[/]")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR", "vim")
    subprocess.run([editor, str(sb_path)])

    # Re-parse edited markdown and update JSON cache
    from .interactive.markdown import markdown_to_storyboard

    md_text = sb_path.read_text()
    updated = markdown_to_storyboard(md_text, project_root=project.root)
    project.save_storyboard(updated)
    console.print("[green]Storyboard updated from markdown edits.[/]")


@app.command()
def export(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
    fmt: Annotated[str, typer.Option("--format", "-f", help="fcpxml|edl|premiere|otio")] = "fcpxml",
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output file path")] = None,
):
    """Export storyboard to NLE timeline format."""
    project = _get_project(path)
    sb = project.load_storyboard()
    if not sb:
        # Try loading from markdown
        sb_path = project.storyboard_path()
        if sb_path.exists():
            from .interactive.markdown import markdown_to_storyboard
            sb = markdown_to_storyboard(sb_path.read_text(), project_root=project.root)
        else:
            console.print("[red]No storyboard found. Run `vlogkit storyboard` first.[/]")
            raise typer.Exit(1)

    from .export.timeline import storyboard_to_timeline
    from .export.formats import export_timeline, FORMAT_EXTENSIONS

    timeline = storyboard_to_timeline(sb)

    if output is None:
        ext = FORMAT_EXTENSIONS.get(fmt, ".fcpxml")
        output = project.cache_dir / f"timeline{ext}"

    result_path = export_timeline(timeline, output, fmt=fmt)
    console.print(f"[green]Exported timeline to {result_path}[/]")


@app.command()
def status(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
):
    """Show project status summary."""
    project = _get_project(path)
    if not project.is_initialized():
        console.print("[red]Not a vlogkit project. Run `vlogkit init` first.[/]")
        raise typer.Exit(1)

    clips = project.scan_clips()
    analyses = project.load_all_analyses()
    sb = project.load_storyboard()

    table = Table(title="vlogkit Project Status")
    table.add_column("Item", style="bold")
    table.add_column("Value")

    table.add_row("Project root", str(project.root))
    table.add_row("Total clips", str(len(clips)))
    table.add_row("Analyzed", str(len(analyses)))
    table.add_row("Storyboard", "Yes" if sb else "No")
    if sb:
        table.add_row("  Sections", str(len(sb.sections)))
        table.add_row("  Included duration", f"{sb.included_duration():.0f}s")
    table.add_row("Storyboard MD", "Yes" if project.storyboard_path().exists() else "No")

    console.print(table)
