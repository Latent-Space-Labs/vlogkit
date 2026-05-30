"""Pydantic response/request schemas for the server API."""
from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel


class ProjectEntryResponse(BaseModel):
    id: str
    path: str
    name: str
    last_opened: float


class RegisterProjectRequest(BaseModel):
    path: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    context: dict | None = None


class ClipMurchScore(BaseModel):
    scene_type: Literal["hook", "narrative", "aesthetic", "commercial"]
    aesthetic: float
    credibility: float
    impact: float
    memorability: float
    fun: float
    composite: float
    rationale: str = ""


class ClipScene(BaseModel):
    start: float
    end: float
    description: str = ""
    tags: list[str] = []
    keyframe_path: str | None = None
    murch: ClipMurchScore | None = None


class ClipAnalysisSummary(BaseModel):
    scenes: list[ClipScene] = []
    summary: str = ""


class ClipSummary(BaseModel):
    filename: str
    size: int
    sha256: str | None = None  # None until analyzed (hash computed at analyze time)
    status: Literal["unanalyzed", "analyzed", "failed"]
    analysis: ClipAnalysisSummary | None = None


class AnalyzeStarted(BaseModel):
    type: Literal["analyze.started"] = "analyze.started"
    job_id: str
    clip_count: int


class AnalyzeProgress(BaseModel):
    type: Literal["analyze.progress"] = "analyze.progress"
    clip_filename: str
    stage: Literal["metadata", "transcribe", "scenes", "vision", "audio", "motion"]
    pct: float  # 0.0 to 1.0


class AnalyzeClipDone(BaseModel):
    type: Literal["analyze.clip_done"] = "analyze.clip_done"
    clip_filename: str
    analysis: dict


class AnalyzeClipFailed(BaseModel):
    type: Literal["analyze.clip_failed"] = "analyze.clip_failed"
    clip_filename: str
    error: str


class AnalyzeComplete(BaseModel):
    type: Literal["analyze.complete"] = "analyze.complete"
    job_id: str
    duration_s: float


class StoryboardRegenStarted(BaseModel):
    type: Literal["storyboard.regen_started"] = "storyboard.regen_started"
    job_id: str


class StoryboardRegenToken(BaseModel):
    type: Literal["storyboard.regen_token"] = "storyboard.regen_token"
    token: str


class StoryboardRegenComplete(BaseModel):
    type: Literal["storyboard.regen_complete"] = "storyboard.regen_complete"
    job_id: str
    storyboard: dict


class StoryboardRegenFailed(BaseModel):
    type: Literal["storyboard.regen_failed"] = "storyboard.regen_failed"
    job_id: str
    error: str


BoardEvent = Union[
    AnalyzeStarted,
    AnalyzeProgress,
    AnalyzeClipDone,
    AnalyzeClipFailed,
    AnalyzeComplete,
    StoryboardRegenStarted,
    StoryboardRegenToken,
    StoryboardRegenComplete,
    StoryboardRegenFailed,
]

# Back-compat alias — existing imports of AnalyzeEvent keep working:
AnalyzeEvent = BoardEvent


class SearchHit(BaseModel):
    clip_filename: str
    clip_sha256: str | None = None
    chunk_start: float
    chunk_end: float
    score: float
    snippet: str = ""


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


class IndexStatus(BaseModel):
    indexed: int
    total: int
    ready: bool


ExportFormat = Literal["fcpxml", "edl", "premiere", "otio"]


class ExportRequest(BaseModel):
    format: ExportFormat
    destination: str


class ExportResponse(BaseModel):
    path: str
    format: ExportFormat
    size_bytes: int


# ---- Captions ----

CaptionFormat = Literal["srt", "vtt", "ass"]


class CaptionsRequest(BaseModel):
    format: CaptionFormat = "srt"


class CaptionsResponse(BaseModel):
    path: str
    format: CaptionFormat
    size_bytes: int
    cue_count: int


# ---- Tighten (silence + filler auto-cut) ----


class TightenRequest(BaseModel):
    dry_run: bool = False


class TightenResponse(BaseModel):
    original_duration: float
    tightened_duration: float
    removed_duration: float
    segments_before: int
    segments_after: int
    saved: bool


# ---- Render (finished MP4) ----


class RenderRequest(BaseModel):
    captions: bool = False
    resolution: str | None = None   # "1080p" | "720p" | "WxH" | None=auto
    fps: float | None = None


class RenderStarted(BaseModel):
    type: Literal["render.started"] = "render.started"
    job_id: str
    resolution: str = ""
    captions: bool = False


class RenderComplete(BaseModel):
    type: Literal["render.complete"] = "render.complete"
    job_id: str
    output_path: str
    size_bytes: int = 0
    duration_s: float = 0.0


class RenderFailed(BaseModel):
    type: Literal["render.failed"] = "render.failed"
    job_id: str
    error: str


# ---- Score job events (new) ----

class ScoreStarted(BaseModel):
    type: Literal["score.started"] = "score.started"
    job_id: str
    total_scenes: int


class ScoreProgress(BaseModel):
    type: Literal["score.progress"] = "score.progress"
    job_id: str
    scored: int
    total_scenes: int
    current_clip: str
    current_scene_index: int


class ScoreClipDone(BaseModel):
    type: Literal["score.clip_done"] = "score.clip_done"
    job_id: str
    clip_filename: str
    average_composite: float


class ScoreComplete(BaseModel):
    type: Literal["score.complete"] = "score.complete"
    job_id: str
    total_scored: int


class ScoreFailed(BaseModel):
    type: Literal["score.failed"] = "score.failed"
    job_id: str
    error: str


# ---- Storyboard multi-agent stage events (new) ----

AgentStage = Literal["director", "editor", "polisher"]


class StoryboardAgentStarted(BaseModel):
    type: Literal["storyboard.agent_started"] = "storyboard.agent_started"
    job_id: str
    stage: AgentStage


class StoryboardAgentComplete(BaseModel):
    type: Literal["storyboard.agent_complete"] = "storyboard.agent_complete"
    job_id: str
    stage: AgentStage
    summary: str = ""


class StoryboardAgentFailed(BaseModel):
    type: Literal["storyboard.agent_failed"] = "storyboard.agent_failed"
    job_id: str
    stage: AgentStage
    reason: str
