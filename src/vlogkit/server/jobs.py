"""Analyze job runner — wraps vlogkit.analyze.pipeline with event emission."""
from __future__ import annotations

import asyncio
import time
import uuid

from vlogkit.project import Project
from vlogkit.server.schemas import (
    AnalyzeClipDone,
    AnalyzeClipFailed,
    AnalyzeComplete,
    AnalyzeStarted,
)
from vlogkit.server.ws import WsBroker


def new_job_id() -> str:
    return uuid.uuid4().hex


async def run_analyze_job(
    broker: WsBroker,
    project_id: str,
    project: Project,
    job_id: str,
) -> None:
    """Run analyze on all clips in project, emitting events.

    Per-clip events are emitted because ``vlogkit.analyze.pipeline.analyze_clip``
    is a per-clip function. Cached analyses (hash match) are still reported as
    ``analyze.clip_done`` so the UI sees one event per clip.
    """
    clips = project.scan_clips()
    started = time.monotonic()
    await broker.publish(
        project_id,
        AnalyzeStarted(job_id=job_id, clip_count=len(clips)),
    )

    # Deferred import — faster-whisper/scenedetect are heavy; don't pay the
    # cost on every server request. Only imported when an analyze job runs.
    from vlogkit.analyze.pipeline import analyze_clip

    for clip in clips:
        try:
            cached = project.load_analysis(clip)
            if cached is not None:
                analysis = cached
            else:
                # Wrap blocking work in to_thread so the event loop keeps running
                # (other WS connections, incoming HTTP, etc.).
                analysis = await asyncio.to_thread(
                    analyze_clip,
                    clip,
                    project.settings,
                    keyframes_dir=project.settings.keyframes_dir(project.root),
                )
                await asyncio.to_thread(project.save_analysis, analysis)
            await broker.publish(
                project_id,
                AnalyzeClipDone(
                    clip_filename=clip.name,
                    analysis=analysis.model_dump(mode="json"),
                ),
            )
        except Exception as e:  # noqa: BLE001 — surface any failure per-clip
            await broker.publish(
                project_id,
                AnalyzeClipFailed(clip_filename=clip.name, error=str(e)),
            )

    await broker.publish(
        project_id,
        AnalyzeComplete(
            job_id=job_id,
            duration_s=time.monotonic() - started,
        ),
    )


async def run_regenerate_job(
    broker: WsBroker,
    project_id: str,
    project: Project,
    job_id: str,
    strategy: str = "chronological",
    context: str = "",
) -> None:
    """Regenerate the project's storyboard via the LLM builder."""
    from vlogkit.server.schemas import (
        StoryboardRegenComplete,
        StoryboardRegenFailed,
        StoryboardRegenStarted,
    )

    await broker.publish(
        project_id, StoryboardRegenStarted(job_id=job_id)
    )
    try:
        from vlogkit.storyboard.builder import build_storyboard

        # Bridge build_storyboard's event_callback into the WS broker
        loop = asyncio.get_running_loop()

        def _agent_event_callback(event_type: str, stage: str, summary_or_reason: str = ""):
            from vlogkit.server.schemas import (
                StoryboardAgentComplete,
                StoryboardAgentFailed,
                StoryboardAgentStarted,
            )
            if event_type == "agent_started":
                evt = StoryboardAgentStarted(job_id=job_id, stage=stage)
            elif event_type == "agent_complete":
                evt = StoryboardAgentComplete(job_id=job_id, stage=stage, summary=summary_or_reason)
            elif event_type == "agent_failed":
                evt = StoryboardAgentFailed(job_id=job_id, stage=stage, reason=summary_or_reason)
            else:
                return
            asyncio.run_coroutine_threadsafe(broker.publish(project_id, evt), loop)

        analyses = project.load_all_analyses()
        sb = await asyncio.to_thread(
            build_storyboard,
            analyses,
            project.root,
            project.settings,
            strategy,
            context,
            _agent_event_callback,
        )
        await asyncio.to_thread(project.save_storyboard, sb)
        await broker.publish(
            project_id,
            StoryboardRegenComplete(
                job_id=job_id,
                storyboard=sb.model_dump(mode="json"),
            ),
        )
    except Exception as exc:  # noqa: BLE001 — surface any failure back to client
        await broker.publish(
            project_id,
            StoryboardRegenFailed(job_id=job_id, error=str(exc)),
        )


async def run_score_job(
    broker: WsBroker,
    project_id: str,
    project: Project,
    job_id: str,
    force: bool = False,
) -> None:
    """Run scoring on all clips, emitting WS events as it goes."""
    from vlogkit.score import scorer as scorer_module
    from vlogkit.server.schemas import (
        ScoreClipDone,
        ScoreComplete,
        ScoreFailed,
        ScoreProgress,
        ScoreStarted,
    )

    # Pre-count total scenes for the started event
    clips = project.scan_clips()
    total_scenes = 0
    for clip in clips:
        analysis = project.load_analysis(clip)
        if analysis is not None:
            total_scenes += len(analysis.scenes)

    await broker.publish(
        project_id,
        ScoreStarted(job_id=job_id, total_scenes=total_scenes),
    )

    loop = asyncio.get_running_loop()

    def progress_callback(event_type: str, **kwargs) -> None:
        """Bridge sync run_scoring to the async broker via the loop."""
        if event_type == "scene_scored":
            evt = ScoreProgress(
                job_id=job_id,
                scored=kwargs["scored"],
                total_scenes=kwargs["total_scenes"],
                current_clip=kwargs["current_clip"],
                current_scene_index=kwargs["current_scene_index"],
            )
        elif event_type == "clip_done":
            evt = ScoreClipDone(
                job_id=job_id,
                clip_filename=kwargs["clip_filename"],
                average_composite=kwargs["average_composite"],
            )
        else:
            return
        asyncio.run_coroutine_threadsafe(broker.publish(project_id, evt), loop)

    try:
        scored = await asyncio.to_thread(
            scorer_module.run_scoring,
            project,
            force,
            progress_callback,
        )
        await broker.publish(
            project_id,
            ScoreComplete(job_id=job_id, total_scored=scored),
        )
    except Exception as e:
        await broker.publish(
            project_id,
            ScoreFailed(job_id=job_id, error=str(e)),
        )


async def run_render_job(
    broker: WsBroker,
    project_id: str,
    project: Project,
    job_id: str,
    captions: bool = False,
    resolution: str | None = None,
    fps: float | None = None,
) -> None:
    """Render the project's storyboard to a finished MP4, emitting WS events.

    Resolves the storyboard (JSON cache, falling back to ``storyboard.md``),
    picks an output resolution/fps (overridable via ``resolution``/``fps``),
    optionally burns in captions, and runs the blocking ffmpeg render in a
    worker thread. Emits ``render.started`` then ``render.complete`` on success,
    or ``render.failed`` at any failure point.
    """
    from vlogkit.captions import render as render_module
    from vlogkit.captions.render import parse_resolution, pick_render_target
    from vlogkit.ffmpeg_util import has_libass, resolve_ffmpeg
    from vlogkit.server.schemas import (
        RenderComplete,
        RenderFailed,
        RenderStarted,
    )

    try:
        # Resolve the storyboard: JSON cache, then markdown fallback.
        sb = project.load_storyboard()
        if sb is None:
            sb_path = project.storyboard_path()
            if sb_path.exists():
                from vlogkit.interactive.markdown import markdown_to_storyboard

                sb = markdown_to_storyboard(
                    sb_path.read_text(), project_root=project.root
                )
        if sb is None:
            await broker.publish(
                project_id,
                RenderFailed(job_id=job_id, error="No storyboard to render"),
            )
            return

        analyses = project.load_all_analyses()

        # Decide output resolution + fps, honoring explicit overrides.
        target_res, target_fps = pick_render_target(sb, analyses)
        override_res = parse_resolution(resolution)
        if override_res is not None:
            target_res = override_res
        if fps is not None:
            target_fps = fps

        ffmpeg_bin = resolve_ffmpeg(project.settings.ffmpeg_path or None)

        # Optional caption burn-in needs a libass-capable ffmpeg.
        subtitle_path = None
        if captions:
            if not has_libass(ffmpeg_bin):
                await broker.publish(
                    project_id,
                    RenderFailed(
                        job_id=job_id,
                        error="Captions requested but ffmpeg has no libass support",
                    ),
                )
                return
            from vlogkit.captions.pipeline import (
                generate_caption_file,
                load_caption_style,
            )

            subtitle_path = project.cache_dir / "captions.ass"
            await asyncio.to_thread(
                generate_caption_file,
                sb,
                analyses,
                fmt="ass",
                output_path=subtitle_path,
                style=load_caption_style(project.root),
            )

        output = project.cache_dir / "render.mp4"
        w, h = target_res

        await broker.publish(
            project_id,
            RenderStarted(
                job_id=job_id,
                resolution=f"{w}x{h}",
                captions=captions,
            ),
        )

        await asyncio.to_thread(
            render_module.render,
            sb,
            output,
            subtitle_path=subtitle_path,
            fps=target_fps,
            ffmpeg_bin=ffmpeg_bin,
            resolution=target_res,
        )

        await broker.publish(
            project_id,
            RenderComplete(
                job_id=job_id,
                output_path=str(output),
                size_bytes=output.stat().st_size,
                duration_s=sb.included_duration(),
            ),
        )
    except Exception as e:  # noqa: BLE001 — surface any failure back to client
        await broker.publish(
            project_id,
            RenderFailed(job_id=job_id, error=str(e)),
        )
