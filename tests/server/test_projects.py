"""Tests for /projects CRUD."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _make_folder(tmp_path: Path, name: str) -> Path:
    folder = tmp_path / name
    folder.mkdir()
    return folder


def test_list_projects_empty(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.get("/projects", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_register_project(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    folder = _make_folder(tmp_path, "my-vlog")
    resp = desktop_client.post(
        "/projects",
        headers=auth_headers,
        json={"path": str(folder)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "my-vlog"
    assert body["path"] == str(folder.resolve())
    assert len(body["id"]) == 16


def test_register_nonexistent_path_returns_404(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    resp = desktop_client.post(
        "/projects",
        headers=auth_headers,
        json={"path": str(tmp_path / "nope")},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "project_path_not_found"


def test_list_after_register_shows_project(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    folder = _make_folder(tmp_path, "my-vlog")
    reg = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()

    resp = desktop_client.get("/projects", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == reg["id"]


def test_get_project_by_id(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    folder = _make_folder(tmp_path, "v")
    reg = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()

    resp = desktop_client.get(f"/projects/{reg['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["path"] == str(folder.resolve())


def test_get_unknown_project_returns_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.get(
        "/projects/0123456789abcdef", headers=auth_headers
    )
    assert resp.status_code == 404


def test_delete_project_forgets_from_registry(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    folder = _make_folder(tmp_path, "v")
    reg = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()

    resp = desktop_client.delete(
        f"/projects/{reg['id']}", headers=auth_headers
    )
    assert resp.status_code == 204
    assert folder.exists()  # files untouched

    resp = desktop_client.get("/projects", headers=auth_headers)
    assert resp.json() == []


def test_projects_routes_require_auth(desktop_client: TestClient) -> None:
    assert desktop_client.get("/projects").status_code == 401
