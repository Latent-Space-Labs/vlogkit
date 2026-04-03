"""Tests for semantic search integration (vlogkit.search)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(tmp_path: Path) -> "Project":
    """Create a minimal initialized Project in a temp directory."""
    from vlogkit.project import Project

    project = Project(tmp_path)
    project.init()
    return project


def _fake_video(tmp_path: Path, name: str = "clip.mp4") -> Path:
    """Create a dummy video file."""
    p = tmp_path / name
    p.write_bytes(b"\x00" * 1024)
    return p


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestSearchConfig:
    def test_search_settings_defaults(self):
        from vlogkit.config import Settings

        s = Settings()
        assert s.gemini_api_key == ""
        assert s.search_chunk_duration == 30
        assert s.search_chunk_overlap == 5
        assert s.search_auto_index is True

    def test_search_db_dir(self, tmp_path: Path):
        from vlogkit.config import Settings

        s = Settings()
        db_dir = s.search_db_dir(tmp_path)
        assert db_dir == tmp_path / ".vlogkit" / "search_db"
        assert db_dir.exists()

    def test_search_config_from_env(self, monkeypatch):
        from vlogkit.config import Settings

        monkeypatch.setenv("VLOGKIT_GEMINI_API_KEY", "test-key-123")
        monkeypatch.setenv("VLOGKIT_SEARCH_CHUNK_DURATION", "60")
        monkeypatch.setenv("VLOGKIT_SEARCH_AUTO_INDEX", "false")

        s = Settings()
        assert s.gemini_api_key == "test-key-123"
        assert s.search_chunk_duration == 60
        assert s.search_auto_index is False


# ---------------------------------------------------------------------------
# Indexer tests
# ---------------------------------------------------------------------------

class TestIndexer:
    @patch("sentrysearch.chunker.is_still_frame_chunk")
    @patch("sentrysearch.chunker.preprocess_chunk")
    @patch("sentrysearch.chunker.chunk_video")
    @patch("sentrysearch.store.SentryStore")
    @patch("sentrysearch.embedder.reset_embedder")
    @patch("sentrysearch.embedder.get_embedder")
    def test_index_clips_skips_indexed(
        self, mock_get_embedder, mock_reset, mock_store_cls,
        mock_chunk, mock_preprocess, mock_still, tmp_path,
    ):
        """Already-indexed clips are skipped."""
        from vlogkit.search.indexer import index_clips

        _fake_video(tmp_path, "clip1.mp4")
        project = _make_project(tmp_path)

        # Store says clip is already indexed
        mock_store = MagicMock()
        mock_store.is_indexed.return_value = True
        mock_store.get_stats.return_value = {
            "total_chunks": 5, "unique_source_files": 1, "source_files": [],
        }
        mock_store_cls.return_value = mock_store

        os.environ["GEMINI_API_KEY"] = "fake-key"
        try:
            result = index_clips(project)
        finally:
            os.environ.pop("GEMINI_API_KEY", None)

        assert result == 0  # nothing new indexed
        mock_chunk.assert_not_called()

    @patch("sentrysearch.chunker.is_still_frame_chunk")
    @patch("sentrysearch.chunker.preprocess_chunk")
    @patch("sentrysearch.chunker.chunk_video")
    @patch("sentrysearch.store.SentryStore")
    @patch("sentrysearch.embedder.reset_embedder")
    @patch("sentrysearch.embedder.get_embedder")
    def test_index_clips_indexes_new(
        self, mock_get_embedder, mock_reset, mock_store_cls,
        mock_chunk, mock_preprocess, mock_still, tmp_path,
    ):
        """New clips get chunked, embedded, and stored."""
        from vlogkit.search.indexer import index_clips

        clip = _fake_video(tmp_path, "new_clip.mp4")
        project = _make_project(tmp_path)

        mock_store = MagicMock()
        mock_store.is_indexed.return_value = False
        mock_store.get_stats.return_value = {
            "total_chunks": 2, "unique_source_files": 1, "source_files": [],
        }
        mock_store_cls.return_value = mock_store

        # chunk_video returns one chunk (put temp chunks inside .vlogkit so scan_clips ignores them)
        chunk_dir = tmp_path / ".vlogkit" / "tmpchunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        chunk_path = str(chunk_dir / "chunk_000.mp4")
        Path(chunk_path).write_bytes(b"\x00")
        mock_chunk.return_value = [{
            "chunk_path": chunk_path,
            "source_file": str(clip.resolve()),
            "start_time": 0.0,
            "end_time": 30.0,
        }]

        mock_still.return_value = False
        mock_preprocess.return_value = chunk_path

        embedder = MagicMock()
        embedder.embed_video_chunk.return_value = [0.1] * 768
        mock_get_embedder.return_value = embedder

        os.environ["GEMINI_API_KEY"] = "fake-key"
        try:
            result = index_clips(project)
        finally:
            os.environ.pop("GEMINI_API_KEY", None)

        assert result == 1
        mock_store.add_chunks.assert_called_once()

    def test_index_clips_no_api_key(self, tmp_path):
        """Returns 0 when no API key is available."""
        from vlogkit.search.indexer import index_clips

        _fake_video(tmp_path, "clip.mp4")
        project = _make_project(tmp_path)

        # Clear any existing key
        old = os.environ.pop("GEMINI_API_KEY", None)
        try:
            result = index_clips(project)
            assert result == 0
        finally:
            if old:
                os.environ["GEMINI_API_KEY"] = old


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------

class TestQuery:
    @patch("sentrysearch.embedder.get_embedder")
    @patch("sentrysearch.embedder.reset_embedder")
    @patch("sentrysearch.search.search_footage")
    @patch("sentrysearch.store.SentryStore")
    def test_search_clips_returns_results(
        self, mock_store_cls, mock_search, mock_reset, mock_get_embedder, tmp_path,
    ):
        from vlogkit.search.query import search_clips

        project = _make_project(tmp_path)

        mock_store = MagicMock()
        mock_store.get_stats.return_value = {"total_chunks": 5}
        mock_store_cls.return_value = mock_store

        expected = [
            {"source_file": "/tmp/a.mp4", "start_time": 0, "end_time": 30, "similarity_score": 0.85},
            {"source_file": "/tmp/b.mp4", "start_time": 60, "end_time": 90, "similarity_score": 0.72},
        ]
        mock_search.return_value = expected

        results = search_clips("sunset over bridge", project, n_results=5)

        assert results == expected
        mock_search.assert_called_once()

    @patch("sentrysearch.store.SentryStore")
    def test_search_clips_empty_index(self, mock_store_cls, tmp_path):
        from vlogkit.search.query import search_clips

        project = _make_project(tmp_path)

        mock_store = MagicMock()
        mock_store.get_stats.return_value = {"total_chunks": 0}
        mock_store_cls.return_value = mock_store

        results = search_clips("anything", project)
        assert results == []

    def test_get_search_stats_no_deps(self, tmp_path):
        """get_search_stats returns a dict when sentrysearch is installed."""
        from vlogkit.search.query import get_search_stats

        project = _make_project(tmp_path)
        result = get_search_stats(project)
        # sentrysearch IS installed in test env, so we get a real dict
        assert isinstance(result, dict)
        assert result["total_chunks"] == 0


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestCLI:
    def test_search_command_exists(self):
        """The search command is registered."""
        from vlogkit.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "natural language" in result.output.lower() or "search" in result.output.lower()

    def test_index_command_exists(self):
        """The index command is registered."""
        from vlogkit.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["index", "--help"])
        assert result.exit_code == 0

    def test_search_stats_command_exists(self):
        """The search-stats command is registered."""
        from vlogkit.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["search-stats", "--help"])
        assert result.exit_code == 0
