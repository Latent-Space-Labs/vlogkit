"""Pydantic response/request schemas for the server API."""
from __future__ import annotations

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
