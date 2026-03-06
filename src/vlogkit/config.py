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

    whisper_model: str = "base"
    whisper_device: str = "auto"

    video_extensions: list[str] = Field(
        default=[".mp4", ".mov", ".avi", ".mkv", ".mts", ".m4v", ".webm"]
    )

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


def get_settings() -> Settings:
    return Settings()
