"""Analysis pipeline — orchestrates metadata + transcription with caching."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..config import Settings
from ..models import ClipAnalysis
from ..project import Project, file_hash
from .metadata import extract_metadata
from .transcribe import transcribe_clip

console = Console()


def analyze_clip(
    clip_path: Path,
    settings: Settings,
) -> ClipAnalysis:
    metadata = extract_metadata(clip_path)

    transcript = []
    try:
        transcript = transcribe_clip(
            clip_path,
            model_size=settings.whisper_model,
            device=settings.whisper_device,
        )
    except Exception as e:
        console.print(f"  [yellow]Transcription failed for {clip_path.name}: {e}[/]")

    full_text = " ".join(seg.text for seg in transcript)
    summary = full_text[:200] + "..." if len(full_text) > 200 else full_text

    return ClipAnalysis(
        metadata=metadata,
        transcript=transcript,
        summary=summary,
        file_hash=file_hash(clip_path),
    )


def run_analysis(project: Project, force: bool = False) -> list[ClipAnalysis]:
    clips = project.scan_clips()
    if not clips:
        console.print("[red]No video clips found.[/]")
        return []

    results: list[ClipAnalysis] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analyzing clips...", total=len(clips))

        for clip in clips:
            progress.update(task, description=f"Analyzing {clip.name}...")

            if not force:
                cached = project.load_analysis(clip)
                if cached:
                    results.append(cached)
                    progress.advance(task)
                    continue

            analysis = analyze_clip(clip, project.settings)
            project.save_analysis(analysis)
            results.append(analysis)
            progress.advance(task)

    console.print(f"[green]Analyzed {len(results)} clips.[/]")
    return results
