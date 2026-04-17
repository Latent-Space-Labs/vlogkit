"""Pydantic response/request schemas for the server API."""
from __future__ import annotations

from typing import Literal

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
