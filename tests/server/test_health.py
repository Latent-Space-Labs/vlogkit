"""Tests for the /healthz liveness probe."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_healthz_unauth_returns_ok(client: TestClient) -> None:
    # No auth_headers fixture — /healthz must work without a token.
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_healthz_ignores_bad_token(client: TestClient) -> None:
    resp = client.get("/healthz", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 200
