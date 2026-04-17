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


class ClipSummary(BaseModel):
    filename: str
    size: int
    sha256: str | None = None  # None until analyzed (hash computed at analyze time)
    status: Literal["unanalyzed", "analyzed", "failed"]
    analysis: dict | None = None  # serialized ClipAnalysis when available


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


AnalyzeEvent = Union[
    AnalyzeStarted,
    AnalyzeProgress,
    AnalyzeClipDone,
    AnalyzeClipFailed,
    AnalyzeComplete,
]
