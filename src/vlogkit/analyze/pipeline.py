"""Analysis pipeline — orchestrates metadata + transcription + scenes + vision with caching."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ..config import Settings
from ..models import ClipAnalysis, SceneSegment
from ..project import Project, file_hash
from .metadata import extract_metadata
from .scenes import detect_scenes, extract_keyframe
from .transcribe import transcribe_clip
from .vision import describe_keyframe

console = Console()


def analyze_clip(
    clip_path: Path,
    settings: Settings,
    with_vision: bool = True,
    keyframes_dir: Path | None = None,
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

    scenes: list[SceneSegment] = []
    try:
        scenes = detect_scenes(clip_path)
    except Exception as e:
        console.print(f"  [yellow]Scene detection failed for {clip_path.name}: {e}[/]")

    if with_vision and scenes and settings.anthropic_api_key:
        kf_dir = keyframes_dir or clip_path.parent
        kf_dir.mkdir(parents=True, exist_ok=True)
        for idx, scene in enumerate(scenes):
            midpoint = (scene.start + scene.end) / 2
            kf_path = kf_dir / f"{clip_path.stem}_scene{idx}.jpg"
            try:
                extract_keyframe(clip_path, midpoint, kf_path)
                scene.keyframe_path = kf_path
                description, tags = describe_keyframe(str(kf_path), settings)
                scene.description = description
                scene.tags = tags
            except Exception as e:
                console.print(f"  [yellow]Vision failed for scene {idx} of {clip_path.name}: {e}[/]")

    full_text = " ".join(seg.text for seg in transcript)
    summary = full_text[:200] + "..." if len(full_text) > 200 else full_text

    return ClipAnalysis(
        metadata=metadata,
        transcript=transcript,
        scenes=scenes,
        summary=summary,
        file_hash=file_hash(clip_path),
    )


def run_analysis(project: Project, force: bool = False, with_vision: bool = True) -> list[ClipAnalysis]:
    clips = project.scan_clips()
    if not clips:
        console.print("[red]No video clips found.[/]")
        return []

    results: list[ClipAnalysis] = []
    keyframes_dir = project.settings.keyframes_dir(project.root)

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
                if cached and (not with_vision or cached.scenes):
                    results.append(cached)
                    progress.advance(task)
                    continue

            analysis = analyze_clip(
                clip,
                project.settings,
                with_vision=with_vision,
                keyframes_dir=keyframes_dir,
            )
            project.save_analysis(analysis)
            results.append(analysis)
            progress.advance(task)

    console.print(f"[green]Analyzed {len(results)} clips.[/]")
    return results
