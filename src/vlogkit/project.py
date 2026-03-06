"""Project state and cache management."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import Settings, get_settings
from .models import ClipAnalysis, Storyboard


def file_hash(path: Path, chunk_size: int = 8192) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()[:16]


class Project:
    def __init__(self, root: Path, settings: Settings | None = None):
        self.root = root.resolve()
        self.settings = settings or get_settings()
        self._cache_dir = self.settings.cache_dir(self.root)

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def scan_clips(self) -> list[Path]:
        clips = []
        for ext in self.settings.video_extensions:
            clips.extend(self.root.glob(f"*{ext}"))
            clips.extend(self.root.glob(f"**/*{ext}"))
        # Deduplicate and sort
        seen: set[Path] = set()
        unique = []
        for c in sorted(clips):
            resolved = c.resolve()
            if resolved not in seen and self.settings.cache_dir_name not in str(resolved):
                seen.add(resolved)
                unique.append(resolved)
        return unique

    def clip_cache_path(self, clip_path: Path) -> Path:
        h = file_hash(clip_path)
        return self.settings.clip_cache_dir(self.root) / f"{clip_path.stem}_{h}.json"

    def load_analysis(self, clip_path: Path) -> ClipAnalysis | None:
        cache_path = self.clip_cache_path(clip_path)
        if not cache_path.exists():
            return None
        try:
            data = json.loads(cache_path.read_text())
            analysis = ClipAnalysis.model_validate(data)
            # Check if file hash still matches
            current_hash = file_hash(clip_path)
            if analysis.file_hash != current_hash:
                return None
            return analysis
        except Exception:
            return None

    def save_analysis(self, analysis: ClipAnalysis) -> None:
        cache_path = self.clip_cache_path(analysis.metadata.path)
        cache_path.write_text(analysis.model_dump_json(indent=2))

    def load_all_analyses(self) -> list[ClipAnalysis]:
        results = []
        for clip in self.scan_clips():
            analysis = self.load_analysis(clip)
            if analysis:
                results.append(analysis)
        return results

    def storyboard_path(self) -> Path:
        return self._cache_dir / self.settings.storyboard_filename

    def load_storyboard(self) -> Storyboard | None:
        sb_json = self._cache_dir / "storyboard.json"
        if not sb_json.exists():
            return None
        try:
            return Storyboard.model_validate_json(sb_json.read_text())
        except Exception:
            return None

    def save_storyboard(self, storyboard: Storyboard) -> None:
        sb_json = self._cache_dir / "storyboard.json"
        sb_json.write_text(storyboard.model_dump_json(indent=2))

    def is_initialized(self) -> bool:
        return self._cache_dir.exists()

    def init(self) -> list[Path]:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        clips = self.scan_clips()
        manifest = self._cache_dir / "manifest.json"
        manifest.write_text(json.dumps(
            {"clips": [str(c) for c in clips]},
            indent=2,
        ))
        return clips
