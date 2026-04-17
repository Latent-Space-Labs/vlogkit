"""Shared fixtures for server tests."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vlogkit.project import Project
from vlogkit.server.app import create_app


@pytest.fixture
def tmp_project(tmp_path: Path) -> Project:
    root = tmp_path / "project"
    root.mkdir()
    return Project(root=root)


@pytest.fixture
def test_token() -> str:
    return "test-token-abc123"


@pytest.fixture
def client(tmp_project: Project, test_token: str) -> TestClient:
    app = create_app(project=tmp_project, token=test_token)
    return TestClient(app)


@pytest.fixture
def auth_headers(test_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {test_token}"}


@pytest.fixture
def sample_video_bytes() -> bytes:
    """Tiny fake "video" bytes for upload/media tests."""
    return b"\x00\x00\x00\x20ftypisom" + b"\x00" * 1024


@pytest.fixture
def sample_video_sha256(sample_video_bytes: bytes) -> str:
    return hashlib.sha256(sample_video_bytes).hexdigest()


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / "projects.json"


@pytest.fixture
def desktop_client(registry_path: Path, test_token: str) -> TestClient:
    from vlogkit.server.app import create_desktop_app
    app = create_desktop_app(registry_path=registry_path, token=test_token)
    return TestClient(app)
