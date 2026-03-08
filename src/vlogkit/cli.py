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
templates_app = typer.Typer(name="templates", help="Manage vlog formula templates")
app.add_typer(templates_app, name="templates")

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
    duration: Annotated[Optional[float], typer.Option("--duration", "-d", help="Target duration in seconds")] = None,
    template: Annotated[Optional[str], typer.Option("--template", "-t", help="Template name (e.g. hook-highlights-cta)")] = None,
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

    sb = build_storyboard(
        analyses,
        project.root,
        project.settings,
        strategy=strategy,
        context=context,
        target_duration=duration,
        template_name=template,
    )
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
def quick(
    path: Annotated[Optional[Path], typer.Argument(help="Project directory")] = None,
    duration: Annotated[float, typer.Option("--duration", "-d", help="Target duration in seconds")] = 60.0,
    template: Annotated[str, typer.Option("--template", "-t", help="Template name")] = "hook-highlights-cta",
    fmt: Annotated[str, typer.Option("--format", "-f", help="Export format")] = "fcpxml",
    context: Annotated[str, typer.Option("--context", "-c", help="Brief description")] = "a recent trip",
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output file path")] = None,
):
    """Quick build: init, analyze, storyboard, and export in one command."""
    project = _get_project(path)

    # Step 1: Init (idempotent)
    clips = project.init()
    console.print(f"[green]Found {len(clips)} clips[/]")

    if not clips:
        console.print("[red]No video clips found in this directory.[/]")
        raise typer.Exit(1)

    # Step 2: Analyze (uses cache)
    from .analyze.pipeline import run_analysis

    console.print("[cyan]Analyzing clips (cached results reused)...[/]")
    run_analysis(project, force=False)

    analyses = project.load_all_analyses()
    if not analyses:
        console.print("[red]Analysis failed — no results produced.[/]")
        raise typer.Exit(1)

    # Step 3: Storyboard
    from .storyboard.builder import build_storyboard
    from .interactive.markdown import storyboard_to_markdown

    sb = build_storyboard(
        analyses,
        project.root,
        project.settings,
        context=context,
        target_duration=duration,
        template_name=template,
    )
    project.save_storyboard(sb)

    md = storyboard_to_markdown(sb)
    project.storyboard_path().write_text(md)

    # Step 4: Export
    from .export.timeline import storyboard_to_timeline
    from .export.formats import export_timeline, FORMAT_EXTENSIONS

    timeline = storyboard_to_timeline(sb)

    if output is None:
        ext = FORMAT_EXTENSIONS.get(fmt, ".fcpxml")
        output = project.cache_dir / f"timeline{ext}"

    result_path = export_timeline(timeline, output, fmt=fmt)

    console.print()
    console.print(f"[bold green]Done![/] {len(sb.sections)} sections, {sb.included_duration():.0f}s included")
    console.print(f"Timeline exported to [bold]{result_path}[/]")
    console.print(f"Storyboard: {project.storyboard_path()}")
    console.print("[dim]Tip: Run `vlogkit review` to fine-tune before re-exporting.[/]")


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
        if sb.target_duration:
            table.add_row("  Target duration", f"{sb.target_duration:.0f}s")
        if sb.template_name:
            table.add_row("  Template", sb.template_name)
    table.add_row("Storyboard MD", "Yes" if project.storyboard_path().exists() else "No")

    console.print(table)


# ---------------------------------------------------------------------------
# Templates sub-commands
# ---------------------------------------------------------------------------


@templates_app.command("list")
def templates_list():
    """List available vlog templates."""
    from .templates import get_all_templates

    all_t = get_all_templates()

    table = Table(title="Vlog Templates")
    table.add_column("Name", style="bold")
    table.add_column("Description")
    table.add_column("Sections", justify="right")
    table.add_column("Built-in", justify="center")

    for name, tmpl in sorted(all_t.items()):
        table.add_row(
            name,
            tmpl.description,
            str(len(tmpl.sections)),
            "yes" if tmpl.builtin else "no",
        )

    console.print(table)


@templates_app.command("show")
def templates_show(
    name: Annotated[str, typer.Argument(help="Template name")],
    duration: Annotated[float, typer.Option("--duration", "-d", help="Target duration for time calculations")] = 60.0,
):
    """Show detailed template breakdown with computed timings."""
    from .templates import get_template

    try:
        tmpl = get_template(name)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)

    console.print(f"[bold]{tmpl.name}[/] — {tmpl.description}")
    if tmpl.editing_style:
        console.print(f"Style: {tmpl.editing_style}")
    console.print()

    table = Table(title=f"Sections (at {duration:.0f}s target)")
    table.add_column("Section", style="bold")
    table.add_column("Duration", justify="right")
    table.add_column("Pct", justify="right")
    table.add_column("Pacing")
    table.add_column("Transition")
    table.add_column("Description")

    cumulative = 0.0
    for sec in tmpl.sections:
        sec_dur = sec.duration_pct * duration
        table.add_row(
            sec.name,
            f"{sec_dur:.0f}s",
            f"{sec.duration_pct * 100:.0f}%",
            sec.pacing,
            sec.transition_hint,
            sec.description[:60],
        )
        cumulative += sec_dur

    console.print(table)
    console.print(f"\nTotal: {cumulative:.0f}s")


@templates_app.command("save")
def templates_save(
    name: Annotated[str, typer.Argument(help="Name for the new template")],
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
):
    """Save current storyboard's section structure as a reusable template."""
    from .templates import VlogTemplate, TemplateSectionSpec, save_template

    project = _get_project(path)
    sb = project.load_storyboard()
    if not sb:
        console.print("[red]No storyboard found. Run `vlogkit storyboard` first.[/]")
        raise typer.Exit(1)

    total = sb.included_duration()
    if total <= 0:
        console.print("[red]Storyboard has no included content.[/]")
        raise typer.Exit(1)

    sections = []
    for sec in sb.sections:
        sec_dur = sum(
            seg.out_point - seg.in_point
            for seg in sec.segments
            if seg.include
        )
        sections.append(TemplateSectionSpec(
            name=sec.title,
            duration_pct=sec_dur / total,
            description=sec.notes or sec.title,
        ))

    tmpl = VlogTemplate(
        name=name,
        description=f"Saved from storyboard: {sb.title}",
        sections=sections,
        builtin=False,
    )

    out_path = save_template(tmpl)
    console.print(f"[green]Template '{name}' saved to {out_path}[/]")
