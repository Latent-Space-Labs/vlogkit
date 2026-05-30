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
    no_vision: Annotated[bool, typer.Option("--no-vision", help="Skip Claude vision keyframe descriptions")] = False,
):
    """Run analysis pipeline (transcribe, detect scenes, describe keyframes). Results are cached."""
    project = _get_project(path)
    if not project.is_initialized():
        console.print("[red]Not a vlogkit project. Run `vlogkit init` first.[/]")
        raise typer.Exit(1)

    from .analyze.pipeline import run_analysis

    if not no_vision and project.settings.anthropic_api_key:
        clips = project.scan_clips()
        if clips:
            console.print(
                f"[dim]Vision: describing scene keyframes via Claude for {len(clips)} clip(s) "
                f"(~$0.02 per scene, typically a few scenes per clip; use --no-vision to skip).[/]"
            )

    run_analysis(project, force=force, with_vision=not no_vision)

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
def score(
    path: Annotated[Optional[Path], typer.Option("--path", "-p", help="Project directory")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Re-score scenes that already have a Murch score")] = False,
):
    """Score every detected scene with Murch-style 5-dim weighted ratings."""
    project = _get_project(path)
    if not project.is_initialized():
        console.print("[red]Not a vlogkit project. Run `vlogkit init` first.[/]")
        raise typer.Exit(1)

    from .score.scorer import run_scoring

    run_scoring(project, force=force)


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


def _load_storyboard_or_exit(project: Project):
    """Load the storyboard from JSON cache, falling back to markdown."""
    sb = project.load_storyboard()
    if sb:
        return sb
    sb_path = project.storyboard_path()
    if sb_path.exists():
        from .interactive.markdown import markdown_to_storyboard
        return markdown_to_storyboard(sb_path.read_text(), project_root=project.root)
    console.print("[red]No storyboard found. Run `vlogkit storyboard` first.[/]")
    raise typer.Exit(1)


@app.command()
def captions(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
    fmt: Annotated[str, typer.Option("--format", "-f", help="srt|vtt|ass")] = "srt",
    burn: Annotated[bool, typer.Option("--burn", help="Render an MP4 with captions burned in (needs ffmpeg+libass)")] = False,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output file path")] = None,
):
    """Generate captions (SRT/VTT/ASS) from the storyboard transcript, optionally burned into an MP4.

    Timings are mapped onto the final edited timeline, so the file lines up with
    an exported/rendered cut. Styling is read from `.vlogkit/caption_style.json`.
    """
    project = _get_project(path)
    sb = _load_storyboard_or_exit(project)

    analyses = project.load_all_analyses()
    if not analyses:
        console.print("[red]No analyses found. Run `vlogkit analyze` first.[/]")
        raise typer.Exit(1)

    from .captions.pipeline import EXTENSIONS, generate_caption_file, load_caption_style
    from .ffmpeg_util import has_libass, resolve_ffmpeg

    if fmt not in EXTENSIONS:
        console.print(f"[red]Unknown format '{fmt}'. Choose: {', '.join(EXTENSIONS)}[/]")
        raise typer.Exit(1)

    style = load_caption_style(project.root)

    if output is None:
        output = project.cache_dir / f"captions{EXTENSIONS[fmt]}"
    sidecar = generate_caption_file(sb, analyses, fmt=fmt, output_path=output, style=style)
    console.print(f"[green]Captions written to {sidecar}[/]")

    if not burn:
        return

    # Burn-in: use an ASS sidecar for styled rendering regardless of the chosen
    # text format, then run ffmpeg to cut + overlay captions in one pass.
    ffmpeg_bin = resolve_ffmpeg(project.settings.ffmpeg_path or None)
    if not has_libass(ffmpeg_bin):
        console.print(
            "[red]Cannot burn captions: no ffmpeg with the libass `subtitles` filter was found.[/]\n"
            "[yellow]Install a libass build (e.g. `brew install ffmpeg-full`) or set VLOGKIT_FFMPEG, then retry.[/]\n"
            f"[dim]The {fmt.upper()} sidecar above still works in any NLE.[/]"
        )
        raise typer.Exit(1)

    from .captions.render import render

    ass_path = sidecar if fmt == "ass" else generate_caption_file(
        sb, analyses, fmt="ass", output_path=project.cache_dir / "captions.ass", style=style
    )
    mp4_out = (output.with_suffix(".mp4") if fmt != "ass" else project.cache_dir / "captioned.mp4")
    console.print(f"[dim]Rendering captioned video via {ffmpeg_bin} → {mp4_out} ...[/]")
    try:
        result = render(sb, mp4_out, subtitle_path=ass_path, ffmpeg_bin=ffmpeg_bin)
    except RuntimeError as e:
        console.print(f"[red]Render failed:[/] {e}")
        raise typer.Exit(1)
    console.print(f"[green]Captioned video rendered to {result}[/]")


def _parse_resolution(spec: str | None) -> tuple[int, int] | None:
    """Parse '1080p'|'720p'|'WxH' into (width, height); None for auto."""
    from .captions.render import parse_resolution

    try:
        return parse_resolution(spec)
    except ValueError as e:
        raise typer.BadParameter(str(e))


@app.command()
def render(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
    captions: Annotated[bool, typer.Option("--captions", help="Burn captions into the video")] = False,
    resolution: Annotated[Optional[str], typer.Option("--resolution", "-r", help="1080p|720p|WxH (default: auto from clips)")] = None,
    fps: Annotated[Optional[float], typer.Option("--fps", help="Output frame rate (default: auto from clips)")] = None,
    audio_cleanup: Annotated[bool, typer.Option("--audio-cleanup", help="Normalize loudness to -14 LUFS")] = False,
    denoise: Annotated[bool, typer.Option("--denoise", help="Apply background noise reduction (with --audio-cleanup)")] = False,
    title_card: Annotated[str, typer.Option("--title-card", help="Overlay this title over the first 3s")] = "",
    lower_thirds: Annotated[bool, typer.Option("--lower-thirds", help="Show each segment's label as a lower-third")] = False,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output MP4 path")] = None,
):
    """Render the storyboard to a finished MP4 — no NLE required.

    Trims and concatenates the included segments in one ffmpeg pass, normalizing
    mixed resolutions/frame-rates. With --captions, captions are generated from
    the transcript and burned in (needs an ffmpeg with libass). --audio-cleanup,
    --title-card, and --lower-thirds add finishing polish (text needs freetype).
    """
    project = _get_project(path)
    sb = _load_storyboard_or_exit(project)

    analyses = project.load_all_analyses()

    from .captions.render import pick_render_target, render as render_video
    from .ffmpeg_util import has_libass, resolve_ffmpeg

    auto_res, auto_fps = pick_render_target(sb, analyses)
    target_res = _parse_resolution(resolution) or auto_res
    target_fps = fps or auto_fps

    ffmpeg_bin = resolve_ffmpeg(project.settings.ffmpeg_path or None)

    subtitle_path = None
    if captions:
        if not has_libass(ffmpeg_bin):
            console.print(
                "[red]--captions needs an ffmpeg with libass.[/] "
                "Install one (e.g. `brew install ffmpeg-full`) or set VLOGKIT_FFMPEG."
            )
            raise typer.Exit(1)
        if not analyses:
            console.print("[red]No analyses found for captions. Run `vlogkit analyze` first.[/]")
            raise typer.Exit(1)
        from .captions.pipeline import generate_caption_file, load_caption_style

        style = load_caption_style(project.root)
        subtitle_path = generate_caption_file(
            sb, analyses, fmt="ass", output_path=project.cache_dir / "captions.ass", style=style
        )

    out = output or (project.cache_dir / "render.mp4")
    console.print(
        f"[dim]Rendering {target_res[0]}x{target_res[1]} @ {target_fps:g}fps via {ffmpeg_bin} → {out} ...[/]"
    )
    try:
        result = render_video(
            sb, out, subtitle_path=subtitle_path, fps=target_fps,
            ffmpeg_bin=ffmpeg_bin, resolution=target_res,
            audio_cleanup=audio_cleanup, denoise=denoise,
            title_card=title_card or None, lower_thirds=lower_thirds,
        )
    except RuntimeError as e:
        console.print(f"[red]Render failed:[/] {e}")
        raise typer.Exit(1)
    console.print(f"[green]Rendered {result}[/] ({sb.included_duration():.0f}s, {len([s for sec in sb.sections for s in sec.segments if s.include])} segments)")


@app.command()
def chapters(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
    intro: Annotated[str, typer.Option("--intro", help="Optional description blurb")] = "",
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Description output path")] = None,
):
    """Generate YouTube chapter markers + a description from the storyboard."""
    project = _get_project(path)
    sb = _load_storyboard_or_exit(project)

    from .publish.chapters import build_chapters, build_description, chapters_to_text

    chs = build_chapters(sb)
    if len(chs) < 3:
        console.print(f"[yellow]Only {len(chs)} chapter(s) — YouTube needs 3+ to show a chapter bar.[/]")
    description = build_description(sb, chs, intro=intro)

    chapters_path = project.cache_dir / "chapters.txt"
    chapters_path.write_text(chapters_to_text(chs) + "\n")
    desc_path = output or (project.cache_dir / "description.md")
    desc_path.write_text(description + "\n")

    console.print(f"[green]Chapters → {chapters_path}[/]  ([bold]{len(chs)}[/] chapters)")
    console.print(f"[green]Description → {desc_path}[/]")
    console.print(f"\n[dim]{chapters_to_text(chs)}[/]")


@app.command()
def shorts(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
    min_dur: Annotated[float, typer.Option("--min", help="Minimum Short duration (s)")] = 15.0,
    max_dur: Annotated[float, typer.Option("--max", help="Maximum Short duration (s)")] = 60.0,
    no_captions: Annotated[bool, typer.Option("--no-captions", help="Skip burned captions")] = False,
    output: Annotated[Optional[Path], typer.Option("--output", "-o")] = None,
):
    """Extract the most engaging moment as a vertical 9:16 Short with captions."""
    project = _get_project(path)
    if not project.load_all_analyses():
        console.print("[red]No analyses found. Run `vlogkit analyze` (and `score`) first.[/]")
        raise typer.Exit(1)

    from .repurpose.shorts import make_short

    console.print("[dim]Picking the highest-impact window and reframing to 9:16…[/]")
    try:
        result = make_short(project, output, min_dur=min_dur, max_dur=max_dur, captions=not no_captions)
    except RuntimeError as e:
        console.print(f"[red]Shorts failed:[/] {e}")
        raise typer.Exit(1)
    console.print(f"[green]Short rendered to {result}[/]")


@app.command()
def highlight(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
    max_duration: Annotated[float, typer.Option("--max", help="Max reel duration (s)")] = 60.0,
    order: Annotated[str, typer.Option("--order", help="chronological|score")] = "chronological",
    output: Annotated[Optional[Path], typer.Option("--output", "-o")] = None,
):
    """Auto-assemble a highlight reel from the top-scored scenes."""
    project = _get_project(path)
    if not project.load_all_analyses():
        console.print("[red]No analyses found. Run `vlogkit analyze` (and `score`) first.[/]")
        raise typer.Exit(1)

    from .repurpose.highlight import make_highlight

    console.print(f"[dim]Selecting top scenes up to {max_duration:.0f}s…[/]")
    try:
        result = make_highlight(project, output, max_duration=max_duration, order=order)
    except RuntimeError as e:
        console.print(f"[red]Highlight failed:[/] {e}")
        raise typer.Exit(1)
    console.print(f"[green]Highlight reel rendered to {result}[/]")


@app.command()
def thumbnail(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
    title: Annotated[str, typer.Option("--title", "-t", help="Overlay title text")] = "",
    count: Annotated[int, typer.Option("--count", "-n", help="Number of candidates")] = 3,
    output_dir: Annotated[Optional[Path], typer.Option("--output", "-o")] = None,
):
    """Generate thumbnail candidates from the most aesthetic scenes."""
    project = _get_project(path)
    if not project.load_all_analyses():
        console.print("[red]No analyses found. Run `vlogkit analyze` (and `score`) first.[/]")
        raise typer.Exit(1)

    from .repurpose.thumbnail import make_thumbnails

    try:
        results = make_thumbnails(project, output_dir, title=title or None, count=count)
    except RuntimeError as e:
        console.print(f"[red]Thumbnail failed:[/] {e}")
        raise typer.Exit(1)
    for r in results:
        console.print(f"[green]Thumbnail → {r}[/]")


@app.command()
def preset(
    name: Annotated[Optional[str], typer.Argument(help="Preset to apply (omit to list)")] = None,
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
):
    """List or apply a content preset (tutorial | vlog | travel)."""
    from .presets import apply_preset, get_preset, list_presets

    if not name:
        table = Table(title="Content presets")
        table.add_column("Name", style="bold")
        table.add_column("Strategy")
        table.add_column("Description")
        for p in list_presets():
            table.add_row(p.name, p.strategy, p.description)
        console.print(table)
        console.print("\n[dim]Apply with: vlogkit preset <name>[/]")
        return

    project = _get_project(path)
    if not project.is_initialized():
        console.print("[red]Not a vlogkit project. Run `vlogkit init` first.[/]")
        raise typer.Exit(1)
    try:
        applied = apply_preset(project, name)
    except (KeyError, ValueError):
        names = ", ".join(p.name for p in list_presets())
        console.print(f"[red]Unknown preset '{name}'. Choose: {names}[/]")
        raise typer.Exit(1)
    console.print(f"[green]Applied preset '{applied.name}'.[/] Storyboard strategy: [bold]{applied.strategy}[/]")
    console.print(f"[dim]Wrote caption_style.json, tighten.json"
                  + (", score_weights.json" if applied.score_weights else "")
                  + f". Run: vlogkit storyboard -s {applied.strategy}[/]")


@app.command()
def broll(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
    count: Annotated[int, typer.Option("--count", "-n", help="Max suggestions")] = 5,
):
    """Suggest B-roll/cutaway opportunities over narration-heavy stretches."""
    project = _get_project(path)
    sb = _load_storyboard_or_exit(project)
    analyses = project.load_all_analyses()
    if not analyses:
        console.print("[red]No analyses found. Run `vlogkit analyze` first.[/]")
        raise typer.Exit(1)

    from .edit.broll import suggest_broll

    suggestions = suggest_broll(sb, analyses, max_suggestions=count)
    if not suggestions:
        console.print("[yellow]No B-roll opportunities found (need narration + aesthetic scenes).[/]")
        return

    table = Table(title="B-roll suggestions")
    table.add_column("At", style="bold", width=12)
    table.add_column("Cut to")
    table.add_column("Over narration")
    for s in suggestions:
        when = f"{_fmt_time(s.timeline_start)}–{_fmt_time(s.timeline_end)}"
        src = f"{Path(s.source_clip).name} @ {s.source_start:.0f}s"
        snippet = (s.trigger_text[:50] + "…") if len(s.trigger_text) > 50 else s.trigger_text
        table.add_row(when, src, snippet)
    console.print(table)


@app.command()
def tighten(
    path: Annotated[Optional[Path], typer.Option("--path", "-p")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Report time saved without modifying the storyboard")] = False,
    render_mp4: Annotated[bool, typer.Option("--render", help="Also render the tightened cut to an MP4")] = False,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="MP4 output path (with --render)")] = None,
):
    """Auto-cut silence + filler words from the storyboard, tightening the edit.

    Splits each segment around dead air and fillers ('um', 'uh', …). Tuning is
    read from `.vlogkit/tighten.json`. The tightened storyboard replaces the
    current one (unless --dry-run), so export/captions/render use it.
    """
    project = _get_project(path)
    sb = _load_storyboard_or_exit(project)

    analyses = project.load_all_analyses()
    if not analyses:
        console.print("[red]No analyses found. Run `vlogkit analyze` first.[/]")
        raise typer.Exit(1)

    from .edit.tighten import load_tighten_config, tighten_storyboard

    config = load_tighten_config(project.root)
    tightened, stats = tighten_storyboard(sb, analyses, config)

    saved = stats.removed_duration
    pct = (saved / stats.original_duration * 100.0) if stats.original_duration else 0.0
    console.print(
        f"[bold]Tightened:[/] {stats.original_duration:.1f}s → {stats.tightened_duration:.1f}s "
        f"([green]−{saved:.1f}s, {pct:.0f}%[/]) | "
        f"segments {stats.segments_before} → {stats.segments_after}"
    )

    if dry_run:
        console.print("[dim]--dry-run: storyboard not modified.[/]")
        return

    project.save_storyboard(tightened)
    from .interactive.markdown import storyboard_to_markdown
    project.storyboard_path().write_text(storyboard_to_markdown(tightened))
    console.print(f"[green]Tightened storyboard saved to {project.storyboard_path()}[/]")

    if not render_mp4:
        return

    from .captions.render import render
    from .ffmpeg_util import resolve_ffmpeg

    ffmpeg_bin = resolve_ffmpeg(project.settings.ffmpeg_path or None)
    mp4_out = output or (project.cache_dir / "tightened.mp4")
    console.print(f"[dim]Rendering tightened cut via {ffmpeg_bin} → {mp4_out} ...[/]")
    try:
        result = render(tightened, mp4_out, subtitle_path=None, ffmpeg_bin=ffmpeg_bin)
    except RuntimeError as e:
        console.print(f"[red]Render failed:[/] {e}")
        raise typer.Exit(1)
    console.print(f"[green]Tightened cut rendered to {result}[/]")


@app.command()
def serve(
    path: Annotated[Optional[Path], typer.Argument(help="Project directory")] = None,
    port: Annotated[int, typer.Option("--port", "-P", help="Server port")] = 8420,
    host: Annotated[str, typer.Option("--host", help="Bind address")] = "0.0.0.0",
):
    """Start upload server for companion app."""
    import secrets

    project = _get_project(path)
    if not project.is_initialized():
        console.print("[yellow]No vlogkit project found — initializing...[/]")
        project.init()

    from .server import run_server
    from .server.app import get_lan_ip

    token = secrets.token_urlsafe(24)
    lan_ip = get_lan_ip()
    url = f"http://{lan_ip}:{port}"

    console.print("\n[bold green]vlogkit upload server[/]")
    console.print(f"Project: {project.root}")
    console.print(f"Listening on: {url}")
    console.print(f"[bold yellow]Auth token:[/] [bold]{token}[/]\n")

    # Show QR code if qrcode is available
    try:
        import qrcode  # type: ignore
        qr = qrcode.QRCode(box_size=1, border=1)
        qr.add_data(url)
        qr.make()
        qr.print_ascii(invert=True)
        console.print()
    except ImportError:
        console.print("[dim](install qrcode for QR display: pip install qrcode)[/]\n")

    run_server(project=project, token=token, host=host, port=port)


@app.command("server")
def server_cmd(
    port: int = 8421,
    registry: Path = typer.Option(
        Path.home() / ".vlogkit" / "projects.json",
        "--registry",
    ),
) -> None:
    """Start the desktop-mode server (for the Electron shell or dev)."""
    import secrets

    from vlogkit.server.app import run_desktop_server

    token = secrets.token_urlsafe(24)
    console.print(f"[bold yellow]Auth token:[/] [bold]{token}[/]")
    typer.echo(f"Port: {port}")
    run_desktop_server(registry_path=registry, token=token, port=port)


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
