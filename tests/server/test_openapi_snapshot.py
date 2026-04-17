"""Locks the OpenAPI schema. Regenerate with VLOGKIT_UPDATE_SNAPSHOTS=1."""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

SNAPSHOT = Path(__file__).parent / "snapshots" / "openapi.json"


def test_openapi_schema_matches_snapshot(desktop_client: TestClient) -> None:
    resp = desktop_client.get("/openapi.json")
    assert resp.status_code == 200
    current = resp.json()

    if os.environ.get("VLOGKIT_UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(current, indent=2, sort_keys=True))
        return

    assert SNAPSHOT.exists(), (
        "snapshot missing. Run VLOGKIT_UPDATE_SNAPSHOTS=1 pytest "
        "tests/server/test_openapi_snapshot.py"
    )
    expected = json.loads(SNAPSHOT.read_text())
    assert current == expected, (
        "OpenAPI schema drifted. If intentional, regenerate with "
        "VLOGKIT_UPDATE_SNAPSHOTS=1 pytest tests/server/test_openapi_snapshot.py"
    )
