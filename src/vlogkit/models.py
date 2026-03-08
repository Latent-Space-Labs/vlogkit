"""Pydantic data models for vlogkit."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class ClipMetadata(BaseModel):
    filename: str
    path: Path
    duration: float
    resolution: tuple[int, int]
    fps: float
    creation_time: datetime | None = None
    file_size: int
    codec: str | None = None


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    confidence: float = 0.0
    words: list[WordTimestamp] = Field(default_factory=list)


class WordTimestamp(BaseModel):
    start: float
    end: float
    word: str
    confidence: float = 0.0


# Re-order so TranscriptSegment can reference WordTimestamp
TranscriptSegment.model_rebuild()


class SceneSegment(BaseModel):
    start: float
    end: float
    keyframe_path: Path | None = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    energy_score: float = 0.0


class AudioAnalysis(BaseModel):
    average_volume: float = 0.0
    has_speech: bool = False
    silence_segments: list[tuple[float, float]] = Field(default_factory=list)
    peak_moments: list[float] = Field(default_factory=list)


class ClipAnalysis(BaseModel):
    metadata: ClipMetadata
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    scenes: list[SceneSegment] = Field(default_factory=list)
    audio: AudioAnalysis | None = None
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)
    file_hash: str = ""


class StoryboardSegment(BaseModel):
    clip_path: Path
    in_point: float = 0.0
    out_point: float = 0.0
    label: str = ""
    transition: str = ""
    include: bool = True


class StoryboardSection(BaseModel):
    title: str
    segments: list[StoryboardSegment] = Field(default_factory=list)
    notes: str = ""


class Storyboard(BaseModel):
    title: str = "Untitled Vlog"
    sections: list[StoryboardSection] = Field(default_factory=list)
    total_duration: float = 0.0
    target_duration: float | None = None
    template_name: str | None = None
    llm_rationale: str = ""

    def included_duration(self) -> float:
        total = 0.0
        for section in self.sections:
            for seg in section.segments:
                if seg.include:
                    total += seg.out_point - seg.in_point
        return total
