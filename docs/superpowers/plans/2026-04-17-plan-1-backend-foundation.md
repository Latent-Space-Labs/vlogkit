# Desktop App — Plan 1: Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow the existing `src/vlogkit/server.py` upload server into a proper `src/vlogkit/server/` package with token auth, project registry, clip routes, Range-aware media streaming, and a pytest suite — the foundation every later plan depends on.

**Architecture:** Replace the single-file `server.py` with a `server/` package (app factory + `routes/` submodules). Preserve existing upload behavior. Add bearer-token middleware bound to a token supplied at launch. Add a JSON-backed `ProjectRegistry` under `~/.vlogkit/projects.json` for tracking recent desktop-app projects without touching the per-project `.vlogkit/` cache. Ship a new `vlogkit server` CLI subcommand that launches the desktop-facing server. No Electron, no Next.js, no WebSockets in this plan — just a clean, typed, tested HTTP API.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, Pydantic v2, pytest, httpx (test client), existing `vlogkit.models` and `vlogkit.project` modules.

---

## File Structure

**New files:**
- `src/vlogkit/server/__init__.py` — re-exports `create_app`, `run_server`
- `src/vlogkit/server/app.py` — FastAPI factory, middleware, router wiring
- `src/vlogkit/server/auth.py` — bearer token dependency
- `src/vlogkit/server/registry.py` — `ProjectRegistry` (JSON-backed recent-projects store)
- `src/vlogkit/server/media.py` — Range-aware video streaming helper
- `src/vlogkit/server/routes/__init__.py`
- `src/vlogkit/server/routes/health.py` — `/healthz` (unauth)
- `src/vlogkit/server/routes/projects.py` — `/projects` CRUD
- `src/vlogkit/server/routes/clips.py` — `/projects/{id}/clips` + `/media/{hash}`
- `src/vlogkit/server/routes/uploads.py` — port of existing `/upload` endpoint
- `src/vlogkit/server/schemas.py` — response models that wrap existing `vlogkit.models`
- `src/vlogkit/server/__main__.py` — enables `python -m vlogkit.server --port X --token Y`
- `tests/server/__init__.py`
- `tests/server/conftest.py` — pytest fixtures (tmp registry, tmp project, TestClient)
- `tests/server/test_health.py`
- `tests/server/test_auth.py`
- `tests/server/test_registry.py`
- `tests/server/test_projects.py`
- `tests/server/test_clips.py`
- `tests/server/test_media.py`
- `tests/server/test_uploads.py` — regression coverage for existing upload flow

**Modified files:**
- `src/vlogkit/server.py` — **deleted** (replaced by package)
- `src/vlogkit/cli.py` — `serve` command rewired to new `run_server`; add `server` subcommand for the desktop-mode launcher
- `pyproject.toml` — move `fastapi`, `uvicorn`, `python-multipart`, `qrcode` out of the `[server]` optional extra and into core deps (the desktop app needs them unconditionally); add `httpx` to dev deps

---

## Task 1: Bootstrap the server package (preserve upload behavior)

**Files:**
- Create: `src/vlogkit/server/__init__.py`
- Create: `src/vlogkit/server/app.py`
- Create: `src/vlogkit/server/routes/__init__.py`
- Create: `src/vlogkit/server/routes/uploads.py`
- Create: `tests/server/__init__.py`
- Create: `tests/server/conftest.py`
- Create: `tests/server/test_uploads.py`
- Delete: `src/vlogkit/server.py`
- Modify: `src/vlogkit/cli.py` (update import)
- Modify: `pyproject.toml`

- [ ] **Step 1: Move fastapi/uvicorn/python-multipart/qrcode into core deps**

Edit `pyproject.toml`. Move these four entries from `[project.optional-dependencies].server` into `[project].dependencies`. Keep `[project.optional-dependencies].server` as an empty list (or remove the block if empty). Add `httpx>=0.27` and `pytest-asyncio>=0.23` to a new `[project.optional-dependencies].dev` group.

```toml
[project]
dependencies = [
    "typer[all]>=0.9",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "faster-whisper>=1.0",
    "stable-ts>=2.0",
    "scenedetect[opencv]>=0.6",
    "opentimelineio>=0.17",
    "anthropic>=0.40",
    "ffmpeg-python>=0.2",
    "rich>=13.0",
    "fastapi>=0.104",
    "uvicorn[standard]>=0.24",
    "python-multipart>=0.0.6",
    "qrcode>=7.0",
]

[project.optional-dependencies]
search = [
    "sentrysearch @ git+https://github.com/ssrajadh/sentrysearch.git",
]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]
```

- [ ] **Step 2: Reinstall and confirm**

Run: `pip install -e '.[dev]'`
Expected: installation completes, `python -c "import fastapi, uvicorn, httpx"` exits 0.

- [ ] **Step 3: Write the upload regression test**

Create `tests/server/__init__.py` (empty).

Create `tests/server/conftest.py`:

```python
"""Shared fixtures for server tests."""
from __future__ import annotations

import hashlib
import shutil
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
```

Create `tests/server/test_uploads.py`:

```python
"""Regression tests for the upload endpoint (ported from legacy server.py)."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_upload_writes_file_and_returns_hash(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_video_bytes: bytes,
    sample_video_sha256: str,
    tmp_project,
) -> None:
    resp = client.post(
        "/upload",
        headers={**auth_headers, "X-SHA256": sample_video_sha256},
        files={"file": ("clip.mp4", sample_video_bytes, "video/mp4")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sha256"] == sample_video_sha256
    assert body["size"] == len(sample_video_bytes)
    assert (tmp_project.root / body["filename"]).read_bytes() == sample_video_bytes


def test_upload_rejects_hash_mismatch(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_video_bytes: bytes,
) -> None:
    resp = client.post(
        "/upload",
        headers={**auth_headers, "X-SHA256": "0" * 64},
        files={"file": ("clip.mp4", sample_video_bytes, "video/mp4")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "hash_mismatch"


def test_upload_disambiguates_filenames(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_video_bytes: bytes,
    sample_video_sha256: str,
    tmp_project,
) -> None:
    for _ in range(2):
        resp = client.post(
            "/upload",
            headers={**auth_headers, "X-SHA256": sample_video_sha256},
            files={"file": ("clip.mp4", sample_video_bytes, "video/mp4")},
        )
        assert resp.status_code == 200

    files = sorted(p.name for p in tmp_project.root.iterdir() if p.is_file())
    assert files == ["clip.mp4", "clip_1.mp4"]
```

- [ ] **Step 4: Run tests to verify they fail (module missing)**

Run: `pytest tests/server/test_uploads.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vlogkit.server.app'`.

- [ ] **Step 5: Create the server package with upload route**

Create `src/vlogkit/server/__init__.py`:

```python
"""vlogkit desktop/companion HTTP server."""
from vlogkit.server.app import create_app, run_server

__all__ = ["create_app", "run_server"]
```

Create `src/vlogkit/server/routes/__init__.py` (empty).

Create `src/vlogkit/server/routes/uploads.py` — port upload logic verbatim from legacy `server.py`:

```python
"""POST /upload — streaming upload with SHA-256 verification."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, UploadFile
from fastapi.responses import JSONResponse

from vlogkit.project import Project
from vlogkit.server.auth import require_token  # created in Task 3

CHUNK_SIZE = 1024 * 1024  # 1 MB


def create_router(project: Project) -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_token)])
    tmp_dir = project.cache_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    @router.post("/upload")
    async def upload(
        file: UploadFile = File(...),
        x_sha256: str | None = Header(None),
    ):
        filename = file.filename or "upload.mp4"
        h = hashlib.sha256()
        fd, tmp_path = tempfile.mkstemp(dir=tmp_dir)
        total = 0
        try:
            with open(fd, "wb") as tmp_f:
                while chunk := await file.read(CHUNK_SIZE):
                    tmp_f.write(chunk)
                    h.update(chunk)
                    total += len(chunk)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

        computed = h.hexdigest()
        if x_sha256 and x_sha256.lower() != computed:
            Path(tmp_path).unlink(missing_ok=True)
            return JSONResponse(
                status_code=400,
                content={
                    "error": "hash_mismatch",
                    "expected": x_sha256.lower(),
                    "computed": computed,
                },
            )

        dest = project.root / filename
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            counter = 1
            while dest.exists():
                dest = project.root / f"{stem}_{counter}{suffix}"
                counter += 1

        shutil.move(tmp_path, dest)
        return {
            "status": "ok",
            "filename": dest.name,
            "size": total,
            "sha256": computed,
        }

    return router
```

Create `src/vlogkit/server/app.py`:

```python
"""FastAPI app factory for the vlogkit desktop/companion server."""
from __future__ import annotations

import socket
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vlogkit.project import Project
from vlogkit.server.routes import uploads


def create_app(project: Project, token: str) -> FastAPI:
    """Build the FastAPI app.

    Args:
        project: Project whose files are served/managed.
        token: Shared-secret bearer token required on all non-health requests.
    """
    app = FastAPI(title="vlogkit server")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Stash shared state on app.state for dependencies to read.
    app.state.project = project
    app.state.token = token

    app.include_router(uploads.create_router(project))

    return app


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def run_server(
    project: Project,
    token: str,
    host: str = "127.0.0.1",
    port: int = 8420,
) -> None:
    """Run the server (used by `vlogkit serve` and `vlogkit server`)."""
    import uvicorn

    app = create_app(project=project, token=token)
    uvicorn.run(app, host=host, port=port, log_level="info")
```

Delete `src/vlogkit/server.py`:

```bash
git rm src/vlogkit/server.py
```

- [ ] **Step 6: Create a stub auth module so imports resolve**

Create `src/vlogkit/server/auth.py` (proper implementation arrives in Task 3):

```python
"""Bearer-token auth dependency. Full implementation in Task 3."""
from __future__ import annotations

from fastapi import Header, HTTPException, Request


async def require_token(
    request: Request,
    authorization: str | None = Header(None),
) -> None:
    expected = request.app.state.token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    supplied = authorization.removeprefix("Bearer ").strip()
    if supplied != expected:
        raise HTTPException(status_code=401, detail="invalid_token")
```

- [ ] **Step 7: Update cli.py to point at the new module**

In `src/vlogkit/cli.py`, find the existing `from vlogkit.server import run_server` import (or equivalent) and leave it — it now resolves through the new package. Find the `serve` command implementation and update its call to pass a token. For backward compatibility of the mobile companion flow, generate a token at launch and print it:

```python
# inside the `serve` command body, where run_server is called today
import secrets
from vlogkit.server import run_server
token = secrets.token_urlsafe(24)
console.print(f"[dim]Auth token:[/] {token}")
run_server(project=project, token=token, host=host, port=port)
```

- [ ] **Step 8: Run the upload tests**

Run: `pytest tests/server/test_uploads.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml src/vlogkit/server/ tests/server/ src/vlogkit/cli.py
git rm src/vlogkit/server.py
git commit -m "feat(server): bootstrap server package, port upload route"
```

---

## Task 2: Health route (`/healthz` — unauth)

**Files:**
- Create: `src/vlogkit/server/routes/health.py`
- Create: `tests/server/test_health.py`
- Modify: `src/vlogkit/server/app.py`

- [ ] **Step 1: Write the failing test**

Create `tests/server/test_health.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/server/test_health.py -v`
Expected: FAIL with 404 (route doesn't exist).

- [ ] **Step 3: Implement the health router**

Create `src/vlogkit/server/routes/health.py`:

```python
"""GET /healthz — unauthenticated liveness probe."""
from __future__ import annotations

from fastapi import APIRouter

from vlogkit import __version__ as _version_or_none


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    def healthz() -> dict[str, str]:
        return {
            "status": "ok",
            "version": _version_or_none or "0.0.0",
        }

    return router
```

If `vlogkit/__init__.py` has no `__version__`, add one:

```python
# src/vlogkit/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 4: Wire the router into the app**

Edit `src/vlogkit/server/app.py`. Add the import and `include_router` call:

```python
from vlogkit.server.routes import health, uploads

# ... inside create_app, BEFORE uploads router so /healthz stays unauth:
app.include_router(health.create_router())
app.include_router(uploads.create_router(project))
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/server/test_health.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/vlogkit/server/routes/health.py src/vlogkit/server/app.py src/vlogkit/__init__.py tests/server/test_health.py
git commit -m "feat(server): add /healthz liveness probe"
```

---

## Task 3: Bearer-token auth middleware

The `auth.py` stub from Task 1 already works — this task adds dedicated tests and locks the behavior in.

**Files:**
- Create: `tests/server/test_auth.py`

- [ ] **Step 1: Write the failing test**

Create `tests/server/test_auth.py`:

```python
"""Tests for bearer-token auth enforcement."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_upload_rejects_missing_authorization(client: TestClient) -> None:
    resp = client.post(
        "/upload",
        files={"file": ("clip.mp4", b"bytes", "video/mp4")},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing_bearer_token"


def test_upload_rejects_non_bearer_scheme(client: TestClient) -> None:
    resp = client.post(
        "/upload",
        headers={"Authorization": "Basic " + "x" * 16},
        files={"file": ("clip.mp4", b"bytes", "video/mp4")},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "missing_bearer_token"


def test_upload_rejects_wrong_token(client: TestClient) -> None:
    resp = client.post(
        "/upload",
        headers={"Authorization": "Bearer the-wrong-one"},
        files={"file": ("clip.mp4", b"bytes", "video/mp4")},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "invalid_token"


def test_upload_accepts_correct_token(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = client.post(
        "/upload",
        headers=auth_headers,
        files={"file": ("clip.mp4", b"bytes", "video/mp4")},
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/server/test_auth.py -v`
Expected: all 4 tests PASS (auth dependency already works from Task 1).

- [ ] **Step 3: Commit**

```bash
git add tests/server/test_auth.py
git commit -m "test(server): lock bearer-token auth behavior"
```

---

## Task 4: Project registry (JSON-backed recent-projects store)

**Files:**
- Create: `src/vlogkit/server/registry.py`
- Create: `tests/server/test_registry.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/server/test_registry.py`:

```python
"""Tests for the JSON-backed ProjectRegistry."""
from __future__ import annotations

from pathlib import Path

import pytest

from vlogkit.server.registry import ProjectRegistry


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / "projects.json"


def test_project_id_is_stable_for_same_path(
    registry_path: Path, tmp_path: Path
) -> None:
    reg_a = ProjectRegistry(registry_path)
    reg_b = ProjectRegistry(registry_path)
    folder = tmp_path / "vlog"
    folder.mkdir()
    id_a = reg_a.register(folder).id
    id_b = reg_b.register(folder).id
    assert id_a == id_b


def test_register_is_idempotent(registry_path: Path, tmp_path: Path) -> None:
    reg = ProjectRegistry(registry_path)
    folder = tmp_path / "vlog"
    folder.mkdir()
    reg.register(folder)
    reg.register(folder)
    assert len(reg.list()) == 1


def test_list_returns_most_recent_first(
    registry_path: Path, tmp_path: Path
) -> None:
    reg = ProjectRegistry(registry_path)
    a = tmp_path / "a"
    a.mkdir()
    b = tmp_path / "b"
    b.mkdir()

    reg.register(a)
    reg.register(b)
    # Re-registering `a` should bump it to the top.
    reg.register(a)

    paths = [p.path for p in reg.list()]
    assert paths == [str(a), str(b)]


def test_forget_removes_entry_but_not_files(
    registry_path: Path, tmp_path: Path
) -> None:
    reg = ProjectRegistry(registry_path)
    folder = tmp_path / "vlog"
    folder.mkdir()
    (folder / "keep.mp4").write_bytes(b"data")

    entry = reg.register(folder)
    reg.forget(entry.id)

    assert reg.list() == []
    assert (folder / "keep.mp4").exists()


def test_get_by_id_returns_none_for_unknown(registry_path: Path) -> None:
    reg = ProjectRegistry(registry_path)
    assert reg.get("does-not-exist") is None


def test_persists_across_instances(
    registry_path: Path, tmp_path: Path
) -> None:
    folder = tmp_path / "vlog"
    folder.mkdir()
    ProjectRegistry(registry_path).register(folder)

    reg2 = ProjectRegistry(registry_path)
    assert len(reg2.list()) == 1
    assert reg2.list()[0].path == str(folder)


def test_register_requires_existing_directory(
    registry_path: Path, tmp_path: Path
) -> None:
    reg = ProjectRegistry(registry_path)
    with pytest.raises(FileNotFoundError):
        reg.register(tmp_path / "does-not-exist")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/server/test_registry.py -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement `ProjectRegistry`**

Create `src/vlogkit/server/registry.py`:

```python
"""Persistent registry of recent vlogkit projects, keyed by folder path hash."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectEntry:
    id: str
    path: str
    name: str
    last_opened: float  # Unix epoch seconds


class ProjectRegistry:
    """JSON-backed list of recent projects.

    Not thread-safe — the server is single-process and calls are serialized
    by asyncio. If concurrency becomes an issue later, add a lock.
    """

    def __init__(self, storage_path: Path) -> None:
        self._path = storage_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _compute_id(folder: Path) -> str:
        # Stable identifier across registry recreations — hash the absolute path.
        return hashlib.sha256(str(folder.resolve()).encode()).hexdigest()[:16]

    def _load(self) -> list[ProjectEntry]:
        if not self._path.exists():
            return []
        try:
            raw = json.loads(self._path.read_text())
        except json.JSONDecodeError:
            return []
        return [ProjectEntry(**item) for item in raw]

    def _save(self, entries: list[ProjectEntry]) -> None:
        self._path.write_text(
            json.dumps([asdict(e) for e in entries], indent=2)
        )

    def register(self, folder: Path) -> ProjectEntry:
        if not folder.is_dir():
            raise FileNotFoundError(f"not a directory: {folder}")
        entry = ProjectEntry(
            id=self._compute_id(folder),
            path=str(folder.resolve()),
            name=folder.name,
            last_opened=time.time(),
        )
        entries = [e for e in self._load() if e.id != entry.id]
        entries.insert(0, entry)
        self._save(entries)
        return entry

    def list(self) -> list[ProjectEntry]:
        return sorted(self._load(), key=lambda e: e.last_opened, reverse=True)

    def get(self, project_id: str) -> ProjectEntry | None:
        for e in self._load():
            if e.id == project_id:
                return e
        return None

    def forget(self, project_id: str) -> bool:
        entries = self._load()
        remaining = [e for e in entries if e.id != project_id]
        if len(remaining) == len(entries):
            return False
        self._save(remaining)
        return True
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/server/test_registry.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/vlogkit/server/registry.py tests/server/test_registry.py
git commit -m "feat(server): add ProjectRegistry with JSON persistence"
```

---

## Task 5: Projects routes (`GET/POST/DELETE /projects`)

Wires the registry to HTTP. Introduces the "desktop mode" of the server where a single sidecar manages many projects (unlike the upload server which is bound to one).

**Files:**
- Create: `src/vlogkit/server/schemas.py`
- Create: `src/vlogkit/server/routes/projects.py`
- Create: `tests/server/test_projects.py`
- Modify: `src/vlogkit/server/app.py`
- Modify: `tests/server/conftest.py`

- [ ] **Step 1: Extend conftest for desktop-mode clients**

Edit `tests/server/conftest.py`. Add a `desktop_client` fixture that uses a registry instead of a single project:

```python
# Append to tests/server/conftest.py
@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / "projects.json"


@pytest.fixture
def desktop_client(registry_path: Path, test_token: str) -> TestClient:
    from vlogkit.server.app import create_desktop_app
    app = create_desktop_app(registry_path=registry_path, token=test_token)
    return TestClient(app)
```

- [ ] **Step 2: Write the failing tests**

Create `tests/server/test_projects.py`:

```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/server/test_projects.py -v`
Expected: FAIL with `ImportError: cannot import name 'create_desktop_app'`.

- [ ] **Step 4: Add schemas**

Create `src/vlogkit/server/schemas.py`:

```python
"""Pydantic response/request schemas for the server API."""
from __future__ import annotations

from pydantic import BaseModel


class ProjectEntryResponse(BaseModel):
    id: str
    path: str
    name: str
    last_opened: float


class RegisterProjectRequest(BaseModel):
    path: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    context: dict | None = None
```

- [ ] **Step 5: Implement the projects router**

Create `src/vlogkit/server/routes/projects.py`:

```python
"""/projects CRUD."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from vlogkit.server.auth import require_token
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import (
    ErrorDetail,
    ProjectEntryResponse,
    RegisterProjectRequest,
)


def _registry(request: Request) -> ProjectRegistry:
    return request.app.state.registry


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects",
        tags=["projects"],
        dependencies=[Depends(require_token)],
    )

    @router.get("", response_model=list[ProjectEntryResponse])
    def list_projects(
        registry: ProjectRegistry = Depends(_registry),
    ) -> list[ProjectEntryResponse]:
        return [ProjectEntryResponse(**e.__dict__) for e in registry.list()]

    @router.post(
        "",
        response_model=ProjectEntryResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def register_project(
        body: RegisterProjectRequest,
        registry: ProjectRegistry = Depends(_registry),
    ) -> ProjectEntryResponse:
        folder = Path(body.path)
        if not folder.is_dir():
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    code="project_path_not_found",
                    message=f"Folder does not exist: {folder}",
                ).model_dump(),
            )
        entry = registry.register(folder)
        return ProjectEntryResponse(**entry.__dict__)

    @router.get("/{project_id}", response_model=ProjectEntryResponse)
    def get_project(
        project_id: str,
        registry: ProjectRegistry = Depends(_registry),
    ) -> ProjectEntryResponse:
        entry = registry.get(project_id)
        if not entry:
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    code="project_not_found",
                    message=f"Unknown project: {project_id}",
                ).model_dump(),
            )
        return ProjectEntryResponse(**entry.__dict__)

    @router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
    def forget_project(
        project_id: str,
        registry: ProjectRegistry = Depends(_registry),
    ) -> None:
        if not registry.forget(project_id):
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    code="project_not_found",
                    message=f"Unknown project: {project_id}",
                ).model_dump(),
            )

    return router
```

- [ ] **Step 6: Add `create_desktop_app` factory**

Edit `src/vlogkit/server/app.py`. Add below `create_app`:

```python
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.routes import projects as projects_routes


def create_desktop_app(registry_path: Path, token: str) -> FastAPI:
    """Build the FastAPI app for desktop mode.

    Unlike ``create_app``, this one manages many projects via a registry
    and is the entrypoint used by the Electron shell.
    """
    app = FastAPI(title="vlogkit desktop server")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.registry = ProjectRegistry(registry_path)
    app.state.token = token

    app.include_router(health.create_router())
    app.include_router(projects_routes.create_router())

    return app
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/server/test_projects.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/vlogkit/server/schemas.py src/vlogkit/server/routes/projects.py src/vlogkit/server/app.py tests/server/test_projects.py tests/server/conftest.py
git commit -m "feat(server): add /projects CRUD and desktop app factory"
```

---

## Task 6: Clips routes (`GET /projects/{id}/clips`, `GET /projects/{id}/clips/{hash}`)

Reads from the existing `.vlogkit/` cache — no analyze work happens here, we just expose what's cached. The analyze job endpoint lives in Plan 3.

**Files:**
- Create: `src/vlogkit/server/routes/clips.py`
- Create: `tests/server/test_clips.py`
- Modify: `src/vlogkit/server/schemas.py`
- Modify: `src/vlogkit/server/app.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/server/test_clips.py`:

```python
"""Tests for /projects/{id}/clips endpoints."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def registered_project(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> tuple[str, Path]:
    folder = tmp_path / "vlog"
    folder.mkdir()
    # Create two fake video files so Project.scan_clips() sees them.
    (folder / "a.mp4").write_bytes(b"\x00" * 64)
    (folder / "b.mov").write_bytes(b"\x00" * 64)
    entry = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()
    return entry["id"], folder


def test_list_clips_returns_unanalyzed_clips(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered_project: tuple[str, Path],
) -> None:
    pid, _ = registered_project
    resp = desktop_client.get(
        f"/projects/{pid}/clips", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    names = sorted(c["filename"] for c in body)
    assert names == ["a.mp4", "b.mov"]
    for c in body:
        assert c["status"] == "unanalyzed"
        assert c["analysis"] is None


def test_list_clips_unknown_project_returns_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.get(
        "/projects/deadbeefdeadbeef/clips", headers=auth_headers
    )
    assert resp.status_code == 404


def test_get_clip_unknown_hash_returns_404(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered_project: tuple[str, Path],
) -> None:
    pid, _ = registered_project
    resp = desktop_client.get(
        f"/projects/{pid}/clips/{'0' * 64}", headers=auth_headers
    )
    assert resp.status_code == 404


def test_clips_route_requires_auth(
    desktop_client: TestClient, registered_project: tuple[str, Path]
) -> None:
    pid, _ = registered_project
    resp = desktop_client.get(f"/projects/{pid}/clips")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/server/test_clips.py -v`
Expected: FAIL (routes don't exist).

- [ ] **Step 3: Add clip schemas**

Edit `src/vlogkit/server/schemas.py`. Add below existing classes:

```python
from typing import Literal


class ClipSummary(BaseModel):
    filename: str
    size: int
    sha256: str | None = None  # None until analyzed (hash computed at analyze time)
    status: Literal["unanalyzed", "analyzed", "failed"]
    analysis: dict | None = None  # serialized ClipAnalysis when available
```

- [ ] **Step 4: Implement the clips router**

Create `src/vlogkit/server/routes/clips.py`:

```python
"""/projects/{id}/clips endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from vlogkit.project import Project
from vlogkit.server.auth import require_token
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ClipSummary, ErrorDetail


def _registry(request: Request) -> ProjectRegistry:
    return request.app.state.registry


def _load_project(registry: ProjectRegistry, project_id: str) -> Project:
    entry = registry.get(project_id)
    if not entry:
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="project_not_found",
                message=f"Unknown project: {project_id}",
            ).model_dump(),
        )
    return Project(root=Path(entry.path))


def _summarize_clip(project: Project, clip_path: Path) -> ClipSummary:
    cached = project.load_clip_analysis(clip_path) if hasattr(
        project, "load_clip_analysis"
    ) else None
    return ClipSummary(
        filename=clip_path.name,
        size=clip_path.stat().st_size,
        sha256=getattr(cached, "sha256", None) if cached else None,
        status="analyzed" if cached else "unanalyzed",
        analysis=cached.model_dump() if cached else None,
    )


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["clips"],
        dependencies=[Depends(require_token)],
    )

    @router.get("/clips", response_model=list[ClipSummary])
    def list_clips(
        project_id: str,
        registry: ProjectRegistry = Depends(_registry),
    ) -> list[ClipSummary]:
        project = _load_project(registry, project_id)
        clips = project.scan_clips()
        return [_summarize_clip(project, c) for c in clips]

    @router.get("/clips/{clip_hash}", response_model=ClipSummary)
    def get_clip(
        project_id: str,
        clip_hash: str,
        registry: ProjectRegistry = Depends(_registry),
    ) -> ClipSummary:
        project = _load_project(registry, project_id)
        for c in project.scan_clips():
            summary = _summarize_clip(project, c)
            if summary.sha256 == clip_hash:
                return summary
        raise HTTPException(
            status_code=404,
            detail=ErrorDetail(
                code="clip_not_found",
                message=f"No clip with hash {clip_hash} in project",
            ).model_dump(),
        )

    return router
```

> **Note on `load_clip_analysis`:** if `Project` doesn't yet expose a method that reads cached `ClipAnalysis` JSON, add it in `src/vlogkit/project.py` before proceeding. Its job is simple: given a clip path, look under `project.cache_dir / "clips" / f"{sha256_prefix}.json"` and return a parsed `ClipAnalysis` or `None`. If that helper already exists under a different name, use it — don't duplicate.

- [ ] **Step 5: Wire the router into the desktop app**

Edit `src/vlogkit/server/app.py`. Inside `create_desktop_app`:

```python
from vlogkit.server.routes import clips as clips_routes
# ...
app.include_router(clips_routes.create_router())
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/server/test_clips.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vlogkit/server/routes/clips.py src/vlogkit/server/schemas.py src/vlogkit/server/app.py tests/server/test_clips.py
git commit -m "feat(server): add /projects/{id}/clips list + detail"
```

---

## Task 7: Range-aware media streaming (`GET /media/{hash}`)

Serves raw video bytes to the `<video>` element with HTTP Range support so scrubbing is cheap. Endpoint lives outside the `/projects/{id}` prefix because the media URL is embedded in `<video src>` tags and a shorter path is friendlier.

**Files:**
- Create: `src/vlogkit/server/media.py`
- Create: `tests/server/test_media.py`
- Modify: `src/vlogkit/server/routes/clips.py` (add `/media` route here, it shares the auth dep)
- Modify: `src/vlogkit/server/app.py` (no changes if clips router already mounted)

- [ ] **Step 1: Write the failing tests**

Create `tests/server/test_media.py`:

```python
"""Tests for /media/{hash} range-aware streaming."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


FAKE_VIDEO = b"VIDEO" * 200  # 1000 bytes


@pytest.fixture
def seeded_project(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> tuple[str, str, Path]:
    folder = tmp_path / "vlog"
    folder.mkdir()
    clip = folder / "clip.mp4"
    clip.write_bytes(FAKE_VIDEO)
    clip_hash = hashlib.sha256(FAKE_VIDEO).hexdigest()
    entry = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()
    return entry["id"], clip_hash, clip


def test_media_returns_full_body_without_range(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project,
) -> None:
    _, clip_hash, _ = seeded_project
    resp = desktop_client.get(f"/media/{clip_hash}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content == FAKE_VIDEO
    assert resp.headers["content-type"] == "video/mp4"
    assert resp.headers["accept-ranges"] == "bytes"


def test_media_honors_range_header(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project,
) -> None:
    _, clip_hash, _ = seeded_project
    resp = desktop_client.get(
        f"/media/{clip_hash}",
        headers={**auth_headers, "Range": "bytes=10-19"},
    )
    assert resp.status_code == 206
    assert resp.content == FAKE_VIDEO[10:20]
    assert resp.headers["content-range"] == f"bytes 10-19/{len(FAKE_VIDEO)}"
    assert resp.headers["content-length"] == "10"


def test_media_open_ended_range(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    seeded_project,
) -> None:
    _, clip_hash, _ = seeded_project
    resp = desktop_client.get(
        f"/media/{clip_hash}",
        headers={**auth_headers, "Range": "bytes=995-"},
    )
    assert resp.status_code == 206
    assert resp.content == FAKE_VIDEO[995:]


def test_media_unknown_hash_returns_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.get(
        f"/media/{'0' * 64}", headers=auth_headers
    )
    assert resp.status_code == 404


def test_media_requires_auth(
    desktop_client: TestClient, seeded_project
) -> None:
    _, clip_hash, _ = seeded_project
    resp = desktop_client.get(f"/media/{clip_hash}")
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/server/test_media.py -v`
Expected: FAIL (route doesn't exist).

- [ ] **Step 3: Implement the range helper**

Create `src/vlogkit/server/media.py`:

```python
"""Range-aware file streaming for /media."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse


def _parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    """Parse an HTTP Range header (only `bytes=X-Y` / `bytes=X-`)."""
    if not range_header.startswith("bytes="):
        raise HTTPException(status_code=416, detail="invalid_range")
    spec = range_header.removeprefix("bytes=")
    start_s, _, end_s = spec.partition("-")
    try:
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else file_size - 1
    except ValueError:
        raise HTTPException(status_code=416, detail="invalid_range")
    if start > end or end >= file_size:
        raise HTTPException(status_code=416, detail="range_out_of_bounds")
    return start, end


def stream_file(request: Request, path: Path):
    if not path.is_file():
        raise HTTPException(status_code=404, detail="media_not_found")
    size = path.stat().st_size
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    range_header = request.headers.get("range")

    if range_header is None:
        return FileResponse(
            path,
            media_type=mime,
            headers={"Accept-Ranges": "bytes"},
        )

    start, end = _parse_range(range_header, size)
    length = end - start + 1

    def iter_bytes():
        with path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_bytes(),
        status_code=206,
        media_type=mime,
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(length),
            "Accept-Ranges": "bytes",
        },
    )
```

- [ ] **Step 4: Add `/media/{hash}` route**

Add to the existing `src/vlogkit/server/routes/clips.py` a second top-level router for `/media`. Append at the bottom of the file:

```python
def create_media_router() -> APIRouter:
    router = APIRouter(
        prefix="",
        tags=["media"],
        dependencies=[Depends(require_token)],
    )

    @router.get("/media/{clip_hash}")
    def stream_media(
        request: Request,
        clip_hash: str,
        registry: ProjectRegistry = Depends(_registry),
    ):
        from vlogkit.server.media import stream_file
        # Search across all registered projects — the hash is globally unique.
        for entry in registry.list():
            project = Project(root=Path(entry.path))
            for c in project.scan_clips():
                import hashlib
                h = hashlib.sha256(c.read_bytes()).hexdigest()
                if h == clip_hash:
                    return stream_file(request, c)
        raise HTTPException(status_code=404, detail="media_not_found")

    return router
```

> **Performance note:** this naive scan hashes every file on every media request — fine for a first pass with small projects but unacceptable at scale. Plan 3 replaces it with a sha256→path index built during analyze. Add a FIXME comment in the route so it isn't forgotten.

Add the FIXME inline above the function:

```python
# FIXME(plan-3): replace linear scan with sha256→path index built during analyze
```

- [ ] **Step 5: Wire the media router**

Edit `src/vlogkit/server/app.py`. Inside `create_desktop_app`, add:

```python
app.include_router(clips_routes.create_media_router())
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/server/test_media.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/vlogkit/server/media.py src/vlogkit/server/routes/clips.py src/vlogkit/server/app.py tests/server/test_media.py
git commit -m "feat(server): add /media/{hash} with Range support"
```

---

## Task 8: CLI entrypoint (`python -m vlogkit.server`)

Electron will spawn the sidecar via `python -m vlogkit.server --port X --token Y`. This task makes that command real.

**Files:**
- Create: `src/vlogkit/server/__main__.py`
- Modify: `src/vlogkit/server/app.py` (add `run_desktop_server`)
- Create: `tests/server/test_entrypoint.py`
- Modify: `src/vlogkit/cli.py` (add `server` Typer subcommand that mirrors it for humans)

- [ ] **Step 1: Write the failing test**

Create `tests/server/test_entrypoint.py`:

```python
"""Smoke test for `python -m vlogkit.server`."""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.timeout(30)
def test_module_entrypoint_starts_and_responds(tmp_path: Path) -> None:
    port = _free_port()
    token = "smoke-test-token"
    registry = tmp_path / "projects.json"

    env = os.environ.copy()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vlogkit.server",
            "--port",
            str(port),
            "--token",
            token,
            "--registry",
            str(registry),
            "--bind",
            "127.0.0.1",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        # Poll /healthz
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1.0)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)
        else:
            stdout, stderr = proc.communicate(timeout=2)
            pytest.fail(
                f"server never became ready. stdout={stdout!r} stderr={stderr!r}"
            )

        # Auth'd /projects
        r = httpx.get(
            f"http://127.0.0.1:{port}/projects",
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )
        assert r.status_code == 200
        assert r.json() == []
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
```

Install pytest-timeout if not already present:

```bash
pip install pytest-timeout
```

Add to `pyproject.toml` dev deps:

```toml
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.23",
    "pytest-timeout>=2.2",
    "httpx>=0.27",
]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/server/test_entrypoint.py -v`
Expected: FAIL (`No module named vlogkit.server.__main__` or similar).

- [ ] **Step 3: Add `run_desktop_server`**

Edit `src/vlogkit/server/app.py`. Append:

```python
def run_desktop_server(
    registry_path: Path,
    token: str,
    host: str = "127.0.0.1",
    port: int = 0,
) -> None:
    """Run the desktop-mode server (used by Electron sidecar)."""
    import uvicorn

    app = create_desktop_app(registry_path=registry_path, token=token)
    uvicorn.run(app, host=host, port=port, log_level="warning")
```

- [ ] **Step 4: Create the module entrypoint**

Create `src/vlogkit/server/__main__.py`:

```python
"""`python -m vlogkit.server` — Electron sidecar entrypoint."""
from __future__ import annotations

import argparse
from pathlib import Path

from vlogkit.server.app import run_desktop_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m vlogkit.server")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", type=str, required=True)
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path.home() / ".vlogkit" / "projects.json",
    )
    parser.add_argument("--bind", type=str, default="127.0.0.1")
    args = parser.parse_args()

    run_desktop_server(
        registry_path=args.registry,
        token=args.token,
        host=args.bind,
        port=args.port,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Add `vlogkit server` subcommand for humans**

Edit `src/vlogkit/cli.py`. Find where other subcommands are registered and add:

```python
@app.command("server")
def server_cmd(
    port: int = 8421,
    registry: Path = typer.Option(
        Path.home() / ".vlogkit" / "projects.json",
        "--registry",
    ),
) -> None:
    """Start the desktop-mode server (for the Electron shell or dev)."""
    import secrets

    from vlogkit.server.app import run_desktop_server

    token = secrets.token_urlsafe(24)
    typer.echo(f"Auth token: {token}")
    typer.echo(f"Port: {port}")
    run_desktop_server(registry_path=registry, token=token, port=port)
```

- [ ] **Step 6: Run the entrypoint test**

Run: `pytest tests/server/test_entrypoint.py -v`
Expected: PASS.

- [ ] **Step 7: Manually verify with `vlogkit server`**

Run in one terminal:

```bash
vlogkit server --port 8421
```

Expected: prints `Auth token: <value>` and `Port: 8421`, stays running.

Run in a second terminal, substituting the real token:

```bash
curl -s http://127.0.0.1:8421/healthz
# Expected: {"status":"ok","version":"0.1.0"}

curl -s -H "Authorization: Bearer <token>" http://127.0.0.1:8421/projects
# Expected: []
```

Kill the server with Ctrl-C. Expected: exits cleanly within 1 s.

- [ ] **Step 8: Commit**

```bash
git add src/vlogkit/server/__main__.py src/vlogkit/server/app.py src/vlogkit/cli.py tests/server/test_entrypoint.py pyproject.toml
git commit -m "feat(server): add python -m vlogkit.server entrypoint"
```

---

## Task 9: OpenAPI schema snapshot test

Locks the API contract so any unintended change forces a spec + schema update. Downstream plans (Electron/Next.js) will generate TS types from this; drift here breaks typecheck there.

**Files:**
- Create: `tests/server/test_openapi_snapshot.py`
- Create: `tests/server/snapshots/openapi.json` (generated first time)

- [ ] **Step 1: Write the snapshot test**

Create `tests/server/test_openapi_snapshot.py`:

```python
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
```

- [ ] **Step 2: Generate the initial snapshot**

Run: `VLOGKIT_UPDATE_SNAPSHOTS=1 pytest tests/server/test_openapi_snapshot.py -v`
Expected: PASS (writes the snapshot file).

- [ ] **Step 3: Re-run without the env var to confirm lock**

Run: `pytest tests/server/test_openapi_snapshot.py -v`
Expected: PASS (reads + matches the snapshot).

- [ ] **Step 4: Commit**

```bash
git add tests/server/test_openapi_snapshot.py tests/server/snapshots/openapi.json
git commit -m "test(server): lock OpenAPI schema snapshot"
```

---

## Task 10: Full-suite verification and README update

Confirm every test passes, the server boots, and docs reflect the new entrypoint.

**Files:**
- Modify: `CLAUDE.md` — add the new `vlogkit server` command to the Commands section and note the `src/vlogkit/server/` module in Architecture.

- [ ] **Step 1: Run the full test suite**

Run: `pytest -v`
Expected: every test in `tests/` passes. No new warnings introduced by this plan.

- [ ] **Step 2: End-to-end smoke**

In one terminal:

```bash
vlogkit server --port 8421
```

Note the printed token. In a second terminal:

```bash
curl -s http://127.0.0.1:8421/healthz
# Expected: {"status":"ok","version":"0.1.0"}

TOK="<paste token>"
mkdir -p /tmp/vlogkit-smoke
touch /tmp/vlogkit-smoke/a.mp4 /tmp/vlogkit-smoke/b.mov

curl -s -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"path":"/tmp/vlogkit-smoke"}' http://127.0.0.1:8421/projects
# Expected: {"id":"<16 hex>","path":"/tmp/vlogkit-smoke","name":"vlogkit-smoke","last_opened":...}

curl -s -H "Authorization: Bearer $TOK" http://127.0.0.1:8421/projects
# Expected: [{...}]

# Use the id from above
PID="<paste id>"
curl -s -H "Authorization: Bearer $TOK" http://127.0.0.1:8421/projects/$PID/clips
# Expected: [{"filename":"a.mp4","size":0,"status":"unanalyzed",...}, {...}]
```

Kill the server with Ctrl-C. Expected: clean exit.

- [ ] **Step 3: Update CLAUDE.md**

Edit `CLAUDE.md`. In the Commands section, add:

```bash
vlogkit server [--port N] [--registry PATH]   # Desktop-mode server (used by the desktop shell)
```

In the Architecture section, replace the existing `Server (server.py)` bullet with:

```
- **Server** (`server/`): FastAPI package with app factory, bearer-token auth, project registry, and route modules (health, projects, clips, media, uploads). Two entrypoints: `create_app` (single-project upload mode used by `vlogkit serve`) and `create_desktop_app` (multi-project desktop mode used by `vlogkit server` / `python -m vlogkit.server`). Requires no optional extras — FastAPI and uvicorn are core deps.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document vlogkit server command and new server package"
```

- [ ] **Step 5: Plan improvements review**

Look back at the work. Write up anything awkward, missing, or worth revisiting in a short review note — these feed into the next chunk's "plan improvements" slot. Capture as `docs/superpowers/plans/2026-04-17-plan-1-review.md` with sections:

- **What regressed / almost regressed**
- **Rough edges** (linear media hash scan is a known one)
- **Deferred items to carry into Plan 2 / 3**
- **Spec gaps discovered during implementation**

Commit:

```bash
git add docs/superpowers/plans/2026-04-17-plan-1-review.md
git commit -m "docs: plan 1 review + carry-over items"
```

- [ ] **Step 6: Verify the iterate loop is done**

- ✅ Build: all code from Tasks 1-9 shipped.
- ✅ Test: 30+ tests across unit + integration + entrypoint smoke.
- ✅ Verify: `curl` smoke against the real running server in Task 10 Step 2.
- ✅ Plan improvements: review note committed in Step 5.
- ➡️ **Iterate:** proceed to Plan 2 (Electron shell + sidecar) only if all of the above pass. If anything is red, cycle back before moving on.

---

## Self-Review Notes

**Spec coverage (§ numbers from the spec):**
- §3 tech stack (backend side) → Tasks 1–8 deliver the FastAPI module with typed models.
- §4 architecture (Electron side) → out of scope, arrives in Plan 2.
- §4.1 sidecar lifecycle → the `python -m vlogkit.server` entrypoint and token handling (Task 8) match the spec exactly.
- §6 backend routes → `/healthz`, `/projects` CRUD, `/clips` list+detail, `/media/{hash}` covered in this plan. `/analyze`, `/storyboard`, `/search`, `/export` are deliberately deferred to Plans 3-6.
- §6 WebSocket → deferred to Plan 3 (first real use case: analyze progress).
- §6 auth → Tasks 1/3 implement bearer-token middleware end-to-end.
- §10 testing → pytest suite + OpenAPI snapshot cover what's in scope for this plan.
- §11 iterate loop → Task 10 Step 5–6 codifies the review gate before moving to Plan 2.

**Placeholder scan:** no `TBD`, `TODO`, or "add appropriate X" handwaves — every step contains the actual code or command. One intentional, surfaced `FIXME(plan-3)` comment documents the linear media scan that Plan 3 will replace.

**Type consistency:** `ProjectEntry` dataclass in the registry ↔ `ProjectEntryResponse` Pydantic model match field-for-field. `ClipSummary` uses `status: Literal["unanalyzed", "analyzed", "failed"]` and the clips route only ever returns `unanalyzed` or `analyzed` in this plan (matches the spec — `failed` first appears in Plan 3 when analyze can fail). `require_token` dependency is referenced from uploads (Task 1), projects (Task 5), clips (Task 6), media (Task 7) with identical signature.
