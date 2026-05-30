"""Configuration via pydantic-settings."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "VLOGKIT_"}

    anthropic_api_key: str = ""
    openai_api_key: str = ""

    claude_model: str = "claude-sonnet-4-20250514"
    claude_vision_model: str = "claude-sonnet-4-20250514"
    score_model: str = "claude-sonnet-4-20250514"  # VLOGKIT_SCORE_MODEL
    storyboard_model: str = "claude-sonnet-4-20250514"  # VLOGKIT_STORYBOARD_MODEL

    whisper_model: str = "base"
    whisper_device: str = "auto"

    # Path to an ffmpeg binary. Leave blank to auto-resolve (prefers a libass
    # build for caption burn-in). VLOGKIT_FFMPEG.
    ffmpeg_path: str = ""

    video_extensions: list[str] = Field(
        default=[".mp4", ".mov", ".avi", ".mkv", ".mts", ".m4v", ".webm"]
    )

    # Search (semantic video search via sentrysearch)
    gemini_api_key: str = ""
    search_chunk_duration: int = 30
    search_chunk_overlap: int = 5
    search_auto_index: bool = True

    cache_dir_name: str = ".vlogkit"
    storyboard_filename: str = "storyboard.md"

    def cache_dir(self, project_root: Path) -> Path:
        d = project_root / self.cache_dir_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def clip_cache_dir(self, project_root: Path) -> Path:
        d = self.cache_dir(project_root) / "clips"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def keyframes_dir(self, project_root: Path) -> Path:
        d = self.cache_dir(project_root) / "keyframes"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def search_db_dir(self, project_root: Path) -> Path:
        d = self.cache_dir(project_root) / "search_db"
        d.mkdir(parents=True, exist_ok=True)
        return d


def get_settings() -> Settings:
    return Settings()
