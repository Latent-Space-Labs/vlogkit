"""Pydantic data models for vlogkit."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

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


SceneType = Literal["hook", "narrative", "aesthetic", "commercial"]


class MurchScore(BaseModel):
    scene_type: SceneType
    aesthetic: float       # 0-100
    credibility: float
    impact: float
    memorability: float
    fun: float
    composite: float       # computed locally from weights, not asked from LLM
    rationale: str = ""


class SceneSegment(BaseModel):
    start: float
    end: float
    keyframe_path: Path | None = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    energy_score: float = 0.0
    murch: MurchScore | None = None


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
    llm_rationale: str = ""

    def included_duration(self) -> float:
        total = 0.0
        for section in self.sections:
            for seg in section.segments:
                if seg.include:
                    total += seg.out_point - seg.in_point
        return total


CaptionPosition = Literal["bottom", "center", "top"]


class CaptionCue(BaseModel):
    """A single on-screen caption, timed against the FINAL rendered timeline."""

    start: float
    end: float
    text: str
    words: list[WordTimestamp] = Field(default_factory=list)


class CaptionStyle(BaseModel):
    """Styling + readability controls for caption rendering.

    Defaults follow BBC/Netflix subtitle conventions: <=42 characters per
    line, <=2 lines, comfortable reading speed.
    """

    font: str = "Arial"
    font_size: int = 48
    primary_color: str = "#FFFFFF"      # resting text colour
    highlight_color: str = "#FFE000"    # active word when karaoke=True
    outline_color: str = "#000000"
    outline: float = 3.0
    shadow: float = 0.0
    position: CaptionPosition = "bottom"
    margin_v: int = 60                  # vertical margin from frame edge (px)
    karaoke: bool = False               # word-by-word highlight (social style)
    animation: Literal["none", "pop", "highlight_box"] = "none"  # animated caption style
    max_chars_per_line: int = 42
    max_lines: int = 2
    max_cps: float = 17.0               # characters per second (readability cap)
    min_duration: float = 1.2           # seconds; merge/extend below this
    max_duration: float = 6.0           # seconds; split above this


# Safe, unambiguous filler tokens. Words like "so", "like", "actually" are
# intentionally excluded by default (they are usually real speech); users can
# add them via .vlogkit/tighten.json for a more aggressive cut.
DEFAULT_FILLERS = ["um", "uh", "er", "ah", "hmm", "mm", "mhm", "umm", "uhh", "erm", "uhm"]


class TightenConfig(BaseModel):
    """Controls for silence + filler-word auto-cut tightening."""

    remove_silence: bool = True
    remove_fillers: bool = True
    min_silence: float = 0.6            # cut silences / word-gaps >= this (seconds)
    pad: float = 0.1                    # breathing room kept around speech (seconds)
    min_keep: float = 0.3              # drop keep-ranges shorter than this (avoid choppy cuts)
    fillers: list[str] = Field(default_factory=lambda: list(DEFAULT_FILLERS))
