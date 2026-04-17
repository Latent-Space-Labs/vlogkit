"""Tests for /projects/{id}/export."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def registered(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> str:
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "a.mp4").write_bytes(b"\x00" * 64)
    entry = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()
    return entry["id"]


def test_export_writes_file(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vlogkit.server.routes import export as export_route

    def fake_run(project, fmt: str, dest: Path) -> None:
        dest.write_text(f"<fake {fmt} export>")

    monkeypatch.setattr(export_route, "_do_export", fake_run)

    dest = tmp_path / "out.fcpxml"
    resp = desktop_client.post(
        f"/projects/{registered}/export",
        headers=auth_headers,
        json={"format": "fcpxml", "destination": str(dest)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["path"] == str(dest)
    assert body["format"] == "fcpxml"
    assert body["size_bytes"] > 0
    assert dest.exists()


def test_export_when_adapter_raises_returns_400(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vlogkit.server.routes import export as export_route

    def fake_run(project, fmt: str, dest: Path) -> None:
        raise ValueError("No storyboard to export")

    monkeypatch.setattr(export_route, "_do_export", fake_run)

    resp = desktop_client.post(
        f"/projects/{registered}/export",
        headers=auth_headers,
        json={"format": "fcpxml", "destination": str(tmp_path / "x.fcpxml")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "export_failed"


def test_export_unknown_project_404(
    desktop_client: TestClient, auth_headers: dict[str, str], tmp_path: Path
) -> None:
    resp = desktop_client.post(
        "/projects/deadbeefdeadbeef/export",
        headers=auth_headers,
        json={"format": "fcpxml", "destination": str(tmp_path / "x.fcpxml")},
    )
    assert resp.status_code == 404


def test_export_requires_auth(
    desktop_client: TestClient, registered: str, tmp_path: Path
) -> None:
    resp = desktop_client.post(
        f"/projects/{registered}/export",
        json={"format": "fcpxml", "destination": str(tmp_path / "x.fcpxml")},
    )
    assert resp.status_code == 401


def test_export_bad_format_returns_422(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    tmp_path: Path,
) -> None:
    resp = desktop_client.post(
        f"/projects/{registered}/export",
        headers=auth_headers,
        json={"format": "invalid", "destination": str(tmp_path / "x")},
    )
    assert resp.status_code == 422
