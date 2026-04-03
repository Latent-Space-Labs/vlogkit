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

    # Auto-index for semantic search if enabled and search deps installed
    if project.settings.search_auto_index:
        try:
            from .search.indexer import index_clips

            console.print("\n[bold]Auto-indexing for semantic search...[/]")
            index_clips(project)
        except ImportError:
            pass  # search deps not installed — skip silently
        except Exception as e:
            console.print(f"[yellow]Search indexing failed (non-blocking): {e}[/]")


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
def serve(
    path: Annotated[Optional[Path], typer.Argument(help="Project directory")] = None,
    port: Annotated[int, typer.Option("--port", "-P", help="Server port")] = 8420,
    host: Annotated[str, typer.Option("--host", help="Bind address")] = "0.0.0.0",
):
    """Start upload server for companion app."""
    project = _get_project(path)
    if not project.is_initialized():
        console.print("[yellow]No vlogkit project found — initializing...[/]")
        project.init()

    try:
        from .server import run_server
    except ImportError:
        console.print("[red]Server dependencies not installed. Run:[/]")
        console.print("  pip install -e '.[server]'")
        raise typer.Exit(1)

    run_server(project, host=host, port=port)


def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


@app.command()
def index(
    path: Annotated[Optional[Path], typer.Option("--path", "-p", help="Project directory")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Re-index all clips")] = False,
):
    """Build or rebuild the semantic search index for video clips."""
    project = _get_project(path)
    if not project.is_initialized():
        console.print("[red]Not a vlogkit project. Run `vlogkit init` first.[/]")
        raise typer.Exit(1)

    try:
        from .search.indexer import index_clips
    except ImportError:
        console.print("[red]Search dependencies not installed. Run:[/]")
        console.print("  pip install -e '.[search]'")
        raise typer.Exit(1)

    index_clips(project, force=force)


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Natural language search query")],
    path: Annotated[Optional[Path], typer.Option("--path", "-p", help="Project directory")] = None,
    results: Annotated[int, typer.Option("--results", "-n", help="Number of results")] = 5,
    trim: Annotated[bool, typer.Option("--trim", "-t", help="Extract matching clip to file")] = False,
    output_dir: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output directory for trimmed clips")] = None,
):
    """Search video clips using natural language (e.g. 'sunset over the bridge')."""
    project = _get_project(path)
    if not project.is_initialized():
        console.print("[red]Not a vlogkit project. Run `vlogkit init` first.[/]")
        raise typer.Exit(1)

    try:
        from .search.query import search_clips
    except ImportError:
        console.print("[red]Search dependencies not installed. Run:[/]")
        console.print("  pip install -e '.[search]'")
        raise typer.Exit(1)

    hits = search_clips(query, project, n_results=results)
    if not hits:
        console.print("[yellow]No results found.[/] Is the search index built?")
        console.print("  Run: vlogkit index")
        return

    # Display results
    table = Table(title=f'Search: "{query}"')
    table.add_column("#", style="bold", width=3)
    table.add_column("Score", width=6)
    table.add_column("Clip")
    table.add_column("Time")

    for i, hit in enumerate(hits, 1):
        basename = Path(hit["source_file"]).name
        start = _fmt_time(hit["start_time"])
        end = _fmt_time(hit["end_time"])
        score = f"{hit['similarity_score']:.2f}"
        table.add_row(str(i), score, basename, f"{start}–{end}")

    console.print(table)

    # Optionally trim the top result
    if trim:
        try:
            from sentrysearch.trimmer import trim_top_results
        except ImportError:
            console.print("[red]sentrysearch not installed for trimming.[/]")
            raise typer.Exit(1)

        out = str(output_dir or (project.cache_dir / "search_clips"))
        clip_paths = trim_top_results(hits, out, count=1)
        for clip_path in clip_paths:
            console.print(f"[green]Saved clip: {clip_path}[/]")


@app.command(name="search-stats")
def search_stats(
    path: Annotated[Optional[Path], typer.Option("--path", "-p", help="Project directory")] = None,
):
    """Show semantic search index statistics."""
    project = _get_project(path)
    if not project.is_initialized():
        console.print("[red]Not a vlogkit project. Run `vlogkit init` first.[/]")
        raise typer.Exit(1)

    try:
        from .search.query import get_search_stats
    except ImportError:
        console.print("[red]Search dependencies not installed. Run:[/]")
        console.print("  pip install -e '.[search]'")
        raise typer.Exit(1)

    stats = get_search_stats(project)
    if stats is None or stats["total_chunks"] == 0:
        console.print("[yellow]Search index is empty.[/] Run `vlogkit index` first.")
        return

    table = Table(title="Search Index")
    table.add_column("Item", style="bold")
    table.add_column("Value")

    table.add_row("Total chunks", str(stats["total_chunks"]))
    table.add_row("Indexed files", str(stats["unique_source_files"]))

    for f in stats["source_files"]:
        exists = Path(f).exists()
        label = "" if exists else " [dim][missing][/]"
        table.add_row("", f"{Path(f).name}{label}")

    console.print(table)


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

    # Search index info (graceful if deps not installed)
    try:
        from .search.query import get_search_stats

        search_stats = get_search_stats(project)
        if search_stats is not None:
            table.add_row("Search index", f"{search_stats['total_chunks']} chunks, {search_stats['unique_source_files']} files")
        else:
            table.add_row("Search index", "[dim]not installed[/]")
    except ImportError:
        table.add_row("Search index", "[dim]not installed[/]")

    console.print(table)
