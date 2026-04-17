# Desktop App — Plan 3: Clips View + Analyze with Live Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the ability to drop into a project and watch its clips analyze in real time. Ships: per-project clips page with live-updating progress cards, `/analyze` HTTP endpoint, WebSocket event stream, and (as a carry-over fix) a sha256→path index that replaces Plan 1's linear `/media/{hash}` scan.

**Architecture:** Backend grows a WebSocket broker (`ws.py`) that holds per-project event queues. `/analyze` starts an `asyncio.Task` that wraps the existing `vlogkit.analyze.pipeline.analyze_project` and emits events as each clip finishes. Backend also builds a `ClipIndex` on each `ProjectRegistry.register()` call so `/media/{hash}` stops rehashing. Frontend adds `/project/[id]` route (with a future-proof `<Tabs>` shell), a clips page listing clips with live progress, and a `useWebSocket` hook that auto-reconnects.

**Tech Stack:** FastAPI WebSockets, asyncio, existing `vlogkit.analyze.pipeline`, existing React 19 + TanStack Query + shadcn primitives (tabs, progress).

---

## File Structure

**Backend:**
- Create: `src/vlogkit/server/ws.py` — per-project event broker
- Create: `src/vlogkit/server/jobs.py` — analyze job runner
- Create: `src/vlogkit/server/clip_index.py` — sha256 → path index
- Modify: `src/vlogkit/server/routes/clips.py` — use the index for `/media`
- Create: `src/vlogkit/server/routes/analyze.py` — `POST /projects/{id}/analyze`, `WS /projects/{id}/events`
- Modify: `src/vlogkit/server/schemas.py` — `AnalyzeStarted`, `AnalyzeProgress`, `AnalyzeClipDone`, `AnalyzeComplete`, `AnalyzeClipFailed` TypedDict/BaseModel shapes
- Modify: `src/vlogkit/server/app.py` — register analyze routes, attach `ClipIndex` and `WsBroker` to `app.state`
- Add: `tests/server/test_clip_index.py`, `tests/server/test_analyze.py`, `tests/server/test_ws.py`

**Frontend:**
- Create: `desktop/web/src/app/project/[id]/layout.tsx` — tabbed shell (Clips / Board / Search; only Clips live this plan)
- Create: `desktop/web/src/app/project/[id]/page.tsx` — redirect to `/clips`
- Create: `desktop/web/src/app/project/[id]/clips/page.tsx` — clips view
- Create: `desktop/web/src/components/clips/clip-card.tsx`
- Create: `desktop/web/src/components/clips/clip-list.tsx`
- Create: `desktop/web/src/components/clips/analyze-button.tsx`
- Create: `desktop/web/src/lib/ws.ts` — typed WS client with reconnect
- Create: `desktop/web/src/lib/events.ts` — event discriminated-union types
- Modify: `desktop/web/src/components/projects/project-list.tsx` — `onOpen` navigates via `useRouter`
- Modify: `desktop/web/src/lib/api.ts` — add `startAnalyze`, `getMediaUrl(hash)` helper
- Modify: `desktop/web/src/app/providers.tsx` — expose a WS provider if needed (likely not — keep subscriptions per-page)
- Modify: `desktop/web/src/lib/query-keys.ts` — extend with clip-level keys

---

## Task 1: ClipIndex (sha256 → path, in-memory, rebuilt on register)

Replaces Plan 1's linear media scan and unblocks `/media/{hash}` performance.

**Files:**
- Create: `src/vlogkit/server/clip_index.py`
- Create: `tests/server/test_clip_index.py`
- Modify: `src/vlogkit/server/app.py` — attach index to `app.state.clip_index`, rebuild on project register
- Modify: `src/vlogkit/server/routes/clips.py` — `create_media_router` uses the index; linear-scan fallback removed

- [ ] **Step 1: Write failing tests**

Create `tests/server/test_clip_index.py`:

```python
"""Tests for the ClipIndex (sha256 → path)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from vlogkit.project import Project
from vlogkit.server.clip_index import ClipIndex


@pytest.fixture
def project_with_clips(tmp_path: Path) -> tuple[Project, dict[str, Path]]:
    root = tmp_path / "proj"
    root.mkdir()
    clips: dict[str, Path] = {}
    for name, body in [("a.mp4", b"A" * 1024), ("b.mov", b"B" * 512)]:
        path = root / name
        path.write_bytes(body)
        clips[hashlib.sha256(body).hexdigest()] = path
    return Project(root=root), clips


def test_index_resolves_full_sha256(
    project_with_clips: tuple[Project, dict[str, Path]]
) -> None:
    project, clips = project_with_clips
    idx = ClipIndex()
    idx.add_project("p1", project)
    for full_hash, path in clips.items():
        assert idx.resolve(full_hash) == path


def test_index_resolves_16_char_prefix(
    project_with_clips: tuple[Project, dict[str, Path]]
) -> None:
    project, clips = project_with_clips
    idx = ClipIndex()
    idx.add_project("p1", project)
    for full_hash, path in clips.items():
        assert idx.resolve(full_hash[:16]) == path


def test_index_returns_none_for_unknown(
    project_with_clips: tuple[Project, dict[str, Path]]
) -> None:
    project, _ = project_with_clips
    idx = ClipIndex()
    idx.add_project("p1", project)
    assert idx.resolve("0" * 64) is None
    assert idx.resolve("0" * 16) is None


def test_remove_project_drops_hashes(
    project_with_clips: tuple[Project, dict[str, Path]]
) -> None:
    project, clips = project_with_clips
    idx = ClipIndex()
    idx.add_project("p1", project)
    idx.remove_project("p1")
    for full_hash in clips:
        assert idx.resolve(full_hash) is None


def test_index_uses_chunked_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Large files must not be read_bytes()'d into memory."""
    # 5 MB synthetic clip
    root = tmp_path / "big"
    root.mkdir()
    big = root / "big.mp4"
    big.write_bytes(b"X" * (5 * 1024 * 1024))

    # Monkey-patch Path.read_bytes to detect misuse
    original_read_bytes = Path.read_bytes
    called_with_big = []

    def guarded(self: Path, *args, **kwargs):
        if self == big:
            called_with_big.append(self)
        return original_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guarded)

    idx = ClipIndex()
    idx.add_project("p1", Project(root=root))
    assert called_with_big == [], (
        "ClipIndex must use chunked hashing, not Path.read_bytes()"
    )
```

- [ ] **Step 2: Run, confirm failure**

`.venv/bin/pytest tests/server/test_clip_index.py -v` → FAIL (ImportError).

- [ ] **Step 3: Implement `ClipIndex`**

Create `src/vlogkit/server/clip_index.py`:

```python
"""In-memory sha256 → Path index, keyed by project id.

Rebuilt when a project is registered. Uses chunked hashing so large clips
don't blow up RAM.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from threading import Lock

from vlogkit.project import Project


def _hash_file(path: Path, chunk: int = 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for blk in iter(lambda: fh.read(chunk), b""):
            hasher.update(blk)
    return hasher.hexdigest()


class ClipIndex:
    """Maps sha256 (full or 16-char prefix) → absolute clip Path."""

    def __init__(self) -> None:
        self._lock = Lock()
        # project_id → {full_sha256: Path}
        self._by_project: dict[str, dict[str, Path]] = {}

    def add_project(self, project_id: str, project: Project) -> None:
        hashes: dict[str, Path] = {}
        for clip in project.scan_clips():
            try:
                h = _hash_file(clip)
            except OSError:
                continue  # skip unreadable
            hashes[h] = clip
        with self._lock:
            self._by_project[project_id] = hashes

    def remove_project(self, project_id: str) -> None:
        with self._lock:
            self._by_project.pop(project_id, None)

    def resolve(self, clip_hash: str) -> Path | None:
        """Look up by full 64-char hash OR 16-char prefix."""
        with self._lock:
            for hashes in self._by_project.values():
                if clip_hash in hashes:
                    return hashes[clip_hash]
                if len(clip_hash) == 16:
                    for full, path in hashes.items():
                        if full.startswith(clip_hash):
                            return path
        return None
```

- [ ] **Step 4: Attach ClipIndex to desktop app state**

In `src/vlogkit/server/app.py`, inside `create_desktop_app`:

```python
from vlogkit.server.clip_index import ClipIndex

# ...
app.state.clip_index = ClipIndex()
```

Also patch `routes/projects.py::register_project` so it populates the index on register:

```python
# inside register_project, after `entry = registry.register(folder)`:
from vlogkit.project import Project
project = Project(root=folder)
request.app.state.clip_index.add_project(entry.id, project)
```

Pass `request: Request` into `register_project` so we can reach `app.state`. Same for `forget_project` — call `clip_index.remove_project(project_id)` after successful `registry.forget`.

- [ ] **Step 5: Rewrite `/media/{hash}` to use the index**

In `src/vlogkit/server/routes/clips.py::create_media_router`, replace the linear scan with:

```python
index: ClipIndex = request.app.state.clip_index
path = index.resolve(clip_hash)
if path is None:
    raise HTTPException(
        status_code=404,
        detail=ErrorDetail(
            code="media_not_found",
            message=f"No clip with hash {clip_hash} found in any registered project",
        ).model_dump(),
    )
return stream_file(request, path)
```

Remove the `FIXME(plan-3)` comment — it's no longer applicable. Remove `hashlib` import from `clips.py` if it's now unused.

- [ ] **Step 6: Regenerate OpenAPI snapshot**

`VLOGKIT_UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/server/test_openapi_snapshot.py -v`

- [ ] **Step 7: Full test run**

`.venv/bin/pytest -v` → expect **60 passed** (56 + 5 new clip_index tests; the `test_media_accepts_16_char_hash_prefix` from Plan 1's fix still passes against the index).

- [ ] **Step 8: Commit**

```bash
git add src/vlogkit/server/clip_index.py src/vlogkit/server/app.py src/vlogkit/server/routes/clips.py src/vlogkit/server/routes/projects.py tests/server/test_clip_index.py tests/server/snapshots/openapi.json
git commit -m "feat(server): add ClipIndex; /media/{hash} uses index, drops linear scan"
```

---

## Task 2: Event schemas + WebSocket broker

**Files:**
- Modify: `src/vlogkit/server/schemas.py`
- Create: `src/vlogkit/server/ws.py`
- Create: `tests/server/test_ws.py`

- [ ] **Step 1: Extend schemas.py with event envelope types**

Append to `src/vlogkit/server/schemas.py`:

```python
from typing import Union


class AnalyzeStarted(BaseModel):
    type: Literal["analyze.started"] = "analyze.started"
    job_id: str
    clip_count: int


class AnalyzeProgress(BaseModel):
    type: Literal["analyze.progress"] = "analyze.progress"
    clip_filename: str
    stage: Literal["metadata", "transcribe", "scenes", "vision", "audio", "motion"]
    pct: float  # 0.0 to 1.0


class AnalyzeClipDone(BaseModel):
    type: Literal["analyze.clip_done"] = "analyze.clip_done"
    clip_filename: str
    analysis: dict


class AnalyzeClipFailed(BaseModel):
    type: Literal["analyze.clip_failed"] = "analyze.clip_failed"
    clip_filename: str
    error: str


class AnalyzeComplete(BaseModel):
    type: Literal["analyze.complete"] = "analyze.complete"
    job_id: str
    duration_s: float


AnalyzeEvent = Union[
    AnalyzeStarted,
    AnalyzeProgress,
    AnalyzeClipDone,
    AnalyzeClipFailed,
    AnalyzeComplete,
]
```

- [ ] **Step 2: Write WS broker tests**

Create `tests/server/test_ws.py`:

```python
"""Tests for the per-project WebSocket broker."""
from __future__ import annotations

import asyncio

import pytest

from vlogkit.server.schemas import AnalyzeStarted
from vlogkit.server.ws import WsBroker


@pytest.mark.asyncio
async def test_broker_fans_out_to_subscribers() -> None:
    broker = WsBroker()
    q1 = broker.subscribe("p1")
    q2 = broker.subscribe("p1")

    evt = AnalyzeStarted(job_id="j1", clip_count=3)
    await broker.publish("p1", evt)

    got1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    got2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert got1 == evt
    assert got2 == evt


@pytest.mark.asyncio
async def test_broker_isolates_projects() -> None:
    broker = WsBroker()
    q_a = broker.subscribe("proj-a")
    q_b = broker.subscribe("proj-b")

    evt = AnalyzeStarted(job_id="j1", clip_count=1)
    await broker.publish("proj-a", evt)

    assert not q_b.qsize()
    assert (await asyncio.wait_for(q_a.get(), timeout=1.0)) == evt


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue() -> None:
    broker = WsBroker()
    q = broker.subscribe("p1")
    broker.unsubscribe("p1", q)
    # Publish should be a no-op for removed subscribers.
    await broker.publish("p1", AnalyzeStarted(job_id="j", clip_count=0))
    assert q.qsize() == 0
```

- [ ] **Step 3: Implement `WsBroker`**

Create `src/vlogkit/server/ws.py`:

```python
"""Per-project pub/sub broker for analyze + other event streams."""
from __future__ import annotations

import asyncio
from collections import defaultdict

from vlogkit.server.schemas import AnalyzeEvent


class WsBroker:
    """In-memory fan-out. One queue per connected WebSocket."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[AnalyzeEvent]]] = defaultdict(list)

    def subscribe(self, project_id: str) -> asyncio.Queue[AnalyzeEvent]:
        q: asyncio.Queue[AnalyzeEvent] = asyncio.Queue()
        self._queues[project_id].append(q)
        return q

    def unsubscribe(self, project_id: str, q: asyncio.Queue[AnalyzeEvent]) -> None:
        lst = self._queues.get(project_id)
        if lst and q in lst:
            lst.remove(q)

    async def publish(self, project_id: str, evt: AnalyzeEvent) -> None:
        for q in list(self._queues.get(project_id, [])):
            await q.put(evt)
```

- [ ] **Step 4: Run tests**

`.venv/bin/pytest tests/server/test_ws.py -v` → 3 passed.

- [ ] **Step 5: Full suite**

`.venv/bin/pytest -v` → expect **63 passed**.

- [ ] **Step 6: Commit**

```bash
git add src/vlogkit/server/ws.py src/vlogkit/server/schemas.py tests/server/test_ws.py
git commit -m "feat(server): add WsBroker and analyze event schemas"
```

---

## Task 3: `/analyze` HTTP + `/events` WebSocket routes

**Files:**
- Create: `src/vlogkit/server/jobs.py` — analyze job wrapper
- Create: `src/vlogkit/server/routes/analyze.py` — HTTP + WS
- Modify: `src/vlogkit/server/app.py` — register router, attach `WsBroker` to `app.state`
- Create: `tests/server/test_analyze.py` — end-to-end test w/ a tiny fixture video

This task uses `vlogkit.analyze.pipeline` directly. If a full real analysis is too slow for tests, the test can monkey-patch the pipeline to yield synthetic events.

- [ ] **Step 1: Write failing test**

Create `tests/server/test_analyze.py`:

```python
"""Tests for /analyze HTTP + WS event stream."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def registered_with_clips(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> tuple[str, Path]:
    folder = tmp_path / "proj"
    folder.mkdir()
    (folder / "a.mp4").write_bytes(b"\x00" * 1024)
    entry = desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    ).json()
    return entry["id"], folder


def test_post_analyze_starts_job_and_returns_id(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered_with_clips: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid, _ = registered_with_clips

    # Patch the pipeline runner with a stub that emits two events then returns.
    from vlogkit.server import jobs

    async def fake_run(broker, project_id, project, job_id):
        from vlogkit.server.schemas import AnalyzeStarted, AnalyzeComplete
        await broker.publish(
            project_id, AnalyzeStarted(job_id=job_id, clip_count=1)
        )
        await broker.publish(
            project_id, AnalyzeComplete(job_id=job_id, duration_s=0.01)
        )

    monkeypatch.setattr(jobs, "run_analyze_job", fake_run)

    resp = desktop_client.post(
        f"/projects/{pid}/analyze", headers=auth_headers
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "job_id" in body


def test_ws_receives_analyze_events(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    test_token: str,
    registered_with_clips: tuple[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pid, _ = registered_with_clips

    from vlogkit.server import jobs

    async def fake_run(broker, project_id, project, job_id):
        from vlogkit.server.schemas import AnalyzeStarted, AnalyzeComplete
        await broker.publish(
            project_id, AnalyzeStarted(job_id=job_id, clip_count=1)
        )
        await asyncio.sleep(0.01)
        await broker.publish(
            project_id, AnalyzeComplete(job_id=job_id, duration_s=0.02)
        )

    monkeypatch.setattr(jobs, "run_analyze_job", fake_run)

    # Connect WS (TestClient uses the `websocket_connect` context)
    with desktop_client.websocket_connect(
        f"/projects/{pid}/events?token={test_token}"
    ) as ws:
        desktop_client.post(f"/projects/{pid}/analyze", headers=auth_headers)

        # Read events until we see analyze.complete
        events = []
        while True:
            msg = ws.receive_text()
            evt = json.loads(msg)
            events.append(evt)
            if evt["type"] == "analyze.complete":
                break

    types = [e["type"] for e in events]
    assert "analyze.started" in types
    assert "analyze.complete" in types


def test_ws_rejects_bad_token(
    desktop_client: TestClient,
    registered_with_clips: tuple[str, Path],
) -> None:
    pid, _ = registered_with_clips
    from fastapi import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with desktop_client.websocket_connect(
            f"/projects/{pid}/events?token=wrong-token"
        ):
            pass
```

- [ ] **Step 2: Implement `jobs.py`**

Create `src/vlogkit/server/jobs.py`:

```python
"""Analyze job runner — wraps vlogkit.analyze.pipeline with event emission."""
from __future__ import annotations

import time
import uuid

from vlogkit.project import Project
from vlogkit.server.schemas import (
    AnalyzeClipDone,
    AnalyzeClipFailed,
    AnalyzeComplete,
    AnalyzeStarted,
)
from vlogkit.server.ws import WsBroker


def new_job_id() -> str:
    return uuid.uuid4().hex


async def run_analyze_job(
    broker: WsBroker,
    project_id: str,
    project: Project,
    job_id: str,
) -> None:
    """Run analyze on all clips in project, emitting events per clip."""
    clips = project.scan_clips()
    started = time.monotonic()
    await broker.publish(
        project_id,
        AnalyzeStarted(job_id=job_id, clip_count=len(clips)),
    )

    # Defer import so the monkeypatched test doesn't spin up ffmpeg/whisper.
    from vlogkit.analyze.pipeline import analyze_clip

    for clip in clips:
        try:
            analysis = analyze_clip(clip, project=project)
            await broker.publish(
                project_id,
                AnalyzeClipDone(
                    clip_filename=clip.name,
                    analysis=analysis.model_dump(mode="json"),
                ),
            )
        except Exception as exc:
            await broker.publish(
                project_id,
                AnalyzeClipFailed(clip_filename=clip.name, error=str(exc)),
            )

    await broker.publish(
        project_id,
        AnalyzeComplete(
            job_id=job_id,
            duration_s=time.monotonic() - started,
        ),
    )
```

Note: `analyze_clip` may or may not exist under that exact name in `vlogkit.analyze.pipeline`. Read that module first and adapt: the goal is to invoke per-clip analysis. If the existing API is `pipeline.analyze_project(project)` with no per-clip hook, wrap it with a loop in `jobs.py` that calls whichever primitive exists. Worst case: use `analyze_project` for the whole batch and emit a synthetic `started → complete` bracket without per-clip events — flag as a Plan-3 rough edge in the review doc.

- [ ] **Step 3: Implement `routes/analyze.py`**

Create `src/vlogkit/server/routes/analyze.py`:

```python
"""/projects/{id}/analyze + /projects/{id}/events (WebSocket)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from vlogkit.project import Project
from vlogkit.server.auth import require_token
from vlogkit.server.jobs import new_job_id, run_analyze_job
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail
from vlogkit.server.ws import WsBroker


def _registry(request: Request) -> ProjectRegistry:
    return request.app.state.registry


def _broker(request: Request) -> WsBroker:
    return request.app.state.ws_broker


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


def create_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/projects/{project_id}/analyze",
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_token)],
        responses={404: {"model": ErrorDetail}},
    )
    async def start_analyze(
        project_id: str,
        request: Request,
        registry: ProjectRegistry = Depends(_registry),
        broker: WsBroker = Depends(_broker),
    ) -> dict[str, str]:
        project = _load_project(registry, project_id)
        job_id = new_job_id()
        asyncio.create_task(
            run_analyze_job(broker, project_id, project, job_id)
        )
        return {"job_id": job_id}

    @router.websocket("/projects/{project_id}/events")
    async def events_ws(ws: WebSocket, project_id: str) -> None:
        token = ws.query_params.get("token")
        if token != ws.app.state.token:
            await ws.close(code=1008)
            return
        await ws.accept()
        broker: WsBroker = ws.app.state.ws_broker
        q = broker.subscribe(project_id)
        try:
            while True:
                evt = await q.get()
                await ws.send_json(evt.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        finally:
            broker.unsubscribe(project_id, q)

    return router
```

- [ ] **Step 4: Wire into `create_desktop_app`**

In `src/vlogkit/server/app.py`:

```python
from vlogkit.server.ws import WsBroker
from vlogkit.server.routes import analyze as analyze_routes

# Inside create_desktop_app, after other app.state assignments:
app.state.ws_broker = WsBroker()

# After other include_router calls:
app.include_router(analyze_routes.create_router())
```

- [ ] **Step 5: Run tests**

`.venv/bin/pytest tests/server/test_analyze.py -v` → 3 passed.

- [ ] **Step 6: Regenerate OpenAPI snapshot**

`VLOGKIT_UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/server/test_openapi_snapshot.py -v`

- [ ] **Step 7: Full suite**

`.venv/bin/pytest -v` → expect **66 passed**.

- [ ] **Step 8: Commit**

```bash
git add src/vlogkit/server/jobs.py src/vlogkit/server/routes/analyze.py src/vlogkit/server/app.py tests/server/test_analyze.py tests/server/snapshots/openapi.json
git commit -m "feat(server): add /analyze HTTP + /events WebSocket"
```

---

## Task 4: Frontend TS types + API client + WS client

**Files:**
- Regenerate: `desktop/web/src/lib/api-types.ts` (via script from Plan 2)
- Modify: `desktop/web/src/lib/api.ts` — add `startAnalyze`, `getMediaUrl`
- Create: `desktop/web/src/lib/events.ts` — TS discriminated union matching `AnalyzeEvent`
- Create: `desktop/web/src/lib/ws.ts` — typed client with auto-reconnect

- [ ] **Step 1: Regenerate TS types**

```bash
cd /Users/bryan/Code/lsl/vlogkit
bash desktop/scripts/gen-api-types.sh
```

Verify the new event shapes land (e.g. `AnalyzeStarted` would appear only if we'd wired it as a response model — since we use it in a WS payload, it's in `components` due to the `responses={...}` declarations or as a standalone model reference; confirm by grep).

- [ ] **Step 2: Extend `lib/api.ts`**

Add to `desktop/web/src/lib/api.ts`:

```typescript
// ... existing imports
import { getBridge } from "./bridge";

// ... inside `export const api = { ... }`:
startAnalyze: (projectId: string) =>
  request<{ job_id: string }>(`/projects/${projectId}/analyze`, {
    method: "POST",
  }),

// ... at the bottom:
export function getMediaUrl(hash: string): string {
  const { apiPort, token } = getBridge();
  // Token is NOT safe to put in a URL for general HTTP; video <src> is fine
  // inside an Electron window where the port + token never leave the process.
  return `http://127.0.0.1:${apiPort}/media/${hash}?token=${encodeURIComponent(token)}`;
}
```

Wait — our auth middleware only accepts `Authorization: Bearer`, not `?token=`. The WS route accepts `?token=` as a side path; we should NOT put the token in the `/media` URL. Better: use a `fetch` with Authorization header and serve the blob URL, OR add a read-only short-lived cookie.

**Minimal fix for this plan:** `getMediaUrl` stays as a `/media/{hash}` path and callers wire it manually into an element via a `fetch` + `URL.createObjectURL` dance OR we defer the `<video>` player to Plan 4. For Plan 3 we don't need media playback — we only need to LIST clips and show progress. So don't export `getMediaUrl` at all this plan. Remove it from the scope. Flag the "how to get a <video src=…> with auth" design decision for Plan 4.

Revise — delete the `getMediaUrl` addition. Only add `startAnalyze` in this task.

- [ ] **Step 3: Create `desktop/web/src/lib/events.ts`**

```typescript
import type { components } from "./api-types";

// If the generator didn't surface the Analyze* models, we spell them
// out by hand. They match schemas.py.

export type AnalyzeStarted = {
  type: "analyze.started";
  job_id: string;
  clip_count: number;
};
export type AnalyzeProgress = {
  type: "analyze.progress";
  clip_filename: string;
  stage: "metadata" | "transcribe" | "scenes" | "vision" | "audio" | "motion";
  pct: number;
};
export type AnalyzeClipDone = {
  type: "analyze.clip_done";
  clip_filename: string;
  analysis: unknown;
};
export type AnalyzeClipFailed = {
  type: "analyze.clip_failed";
  clip_filename: string;
  error: string;
};
export type AnalyzeComplete = {
  type: "analyze.complete";
  job_id: string;
  duration_s: number;
};

export type AnalyzeEvent =
  | AnalyzeStarted
  | AnalyzeProgress
  | AnalyzeClipDone
  | AnalyzeClipFailed
  | AnalyzeComplete;
```

- [ ] **Step 4: Create `desktop/web/src/lib/ws.ts`**

```typescript
import type { AnalyzeEvent } from "./events";
import { getBridge } from "./bridge";

export function connectEventStream(
  projectId: string,
  onEvent: (evt: AnalyzeEvent) => void,
): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let backoff = 500;

  function open() {
    const { apiPort, token } = getBridge();
    if (!apiPort || !token) {
      // Retry until bridge is ready (first paint / SSR hydration quirk).
      if (!closed) setTimeout(open, 500);
      return;
    }
    const url = `ws://127.0.0.1:${apiPort}/projects/${projectId}/events?token=${encodeURIComponent(token)}`;
    ws = new WebSocket(url);
    ws.onmessage = (m) => {
      try {
        onEvent(JSON.parse(m.data));
      } catch (e) {
        console.error("ws parse error", e);
      }
    };
    ws.onopen = () => {
      backoff = 500;
    };
    ws.onclose = () => {
      if (closed) return;
      setTimeout(open, backoff);
      backoff = Math.min(backoff * 2, 8000);
    };
    ws.onerror = () => {
      ws?.close();
    };
  }

  open();
  return () => {
    closed = true;
    ws?.close();
  };
}
```

- [ ] **Step 5: Typecheck + build**

```bash
cd desktop/web
npx tsc --noEmit
npm run build
```

- [ ] **Step 6: Commit**

```bash
git add desktop/web/src/lib
git commit -m "feat(desktop): TS event types + WS client + startAnalyze API"
```

---

## Task 5: Clips page + tabbed project layout

**Files:**
- Create: `desktop/web/src/app/project/[id]/layout.tsx`
- Create: `desktop/web/src/app/project/[id]/page.tsx`
- Create: `desktop/web/src/app/project/[id]/clips/page.tsx`
- Create: `desktop/web/src/components/clips/clip-card.tsx`
- Create: `desktop/web/src/components/clips/clip-list.tsx`
- Create: `desktop/web/src/components/clips/analyze-button.tsx`
- Modify: `desktop/web/src/components/projects/project-list.tsx` — wire `onOpen` to `next/navigation`'s `useRouter`
- Modify: `desktop/web/src/lib/query-keys.ts` — add `clips` keys if not already present

Static export note: Next.js `output: "export"` does NOT support dynamic routes without `generateStaticParams`. Workaround: use a query-param instead of a path segment. Change the route from `/project/[id]/clips` to `/project?id=abc&tab=clips`.

**Revised routes:**
- `/project?id=abc&tab=clips` — clips view
- `/project?id=abc&tab=board` — placeholder (future)
- `/project?id=abc&tab=search` — placeholder (future)

- [ ] **Step 1: `desktop/web/src/app/project/page.tsx`**

```tsx
"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { Suspense } from "react";
import { ClipsTab } from "@/components/clips/clip-list";

function ProjectInner() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const tab = params.get("tab") ?? "clips";

  if (!id) {
    return (
      <main className="max-w-3xl mx-auto px-8 py-16">
        <p className="text-[var(--color-muted)]">No project id.</p>
      </main>
    );
  }

  return (
    <main className="max-w-5xl mx-auto px-8 py-10">
      <header className="mb-6">
        <button
          onClick={() => router.push("/")}
          className="text-sm text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
        >
          ← All projects
        </button>
        <div className="mt-2 flex items-center gap-4">
          <h2 className="text-2xl font-bold">Project</h2>
          <nav className="flex gap-1">
            {(["clips", "board", "search"] as const).map((t) => (
              <button
                key={t}
                onClick={() => router.push(`/project?id=${id}&tab=${t}`)}
                className={
                  "px-3 py-1 rounded-[4px] text-sm " +
                  (t === tab
                    ? "bg-[var(--color-accent)] text-white"
                    : "text-[var(--color-muted)] hover:text-[var(--color-foreground)]")
                }
              >
                {t}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {tab === "clips" && <ClipsTab projectId={id} />}
      {tab === "board" && <Placeholder name="Storyboard editor — Plan 4" />}
      {tab === "search" && <Placeholder name="Semantic search — Plan 5" />}
    </main>
  );
}

function Placeholder({ name }: { name: string }) {
  return (
    <p className="text-[var(--color-muted)] py-16 text-center">{name}</p>
  );
}

export default function ProjectPage() {
  return (
    <Suspense>
      <ProjectInner />
    </Suspense>
  );
}
```

- [ ] **Step 2: `desktop/web/src/components/clips/clip-card.tsx`**

```tsx
import type { ClipSummary } from "@/lib/api";
import type { AnalyzeProgress } from "@/lib/events";

export function ClipCard({
  clip,
  progress,
}: {
  clip: ClipSummary;
  progress?: AnalyzeProgress;
}) {
  const analyzed = clip.status === "analyzed";
  return (
    <div
      className="bg-white rounded-[12px] border border-[var(--color-border-whisper)] p-4"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="flex items-center justify-between">
        <div className="font-semibold">{clip.filename}</div>
        <StatusPill status={clip.status} />
      </div>
      <div className="text-xs text-[var(--color-placeholder)] mt-1">
        {(clip.size / 1024 / 1024).toFixed(1)} MB
      </div>
      {!analyzed && progress && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-xs text-[var(--color-muted)]">
            <span>{progress.stage}</span>
            <span>{Math.round(progress.pct * 100)}%</span>
          </div>
          <div className="h-1 bg-[var(--color-background-alt)] rounded-full mt-1 overflow-hidden">
            <div
              className="h-full bg-[var(--color-accent)] transition-[width]"
              style={{ width: `${progress.pct * 100}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: ClipSummary["status"] }) {
  const styles = {
    unanalyzed: "bg-[var(--color-background-alt)] text-[var(--color-muted)]",
    analyzed: "bg-[var(--color-badge-bg)] text-[var(--color-badge-text)]",
    failed: "bg-red-50 text-red-700",
  }[status];
  return (
    <span
      className={`text-xs font-semibold px-2 py-0.5 rounded-full ${styles}`}
    >
      {status}
    </span>
  );
}
```

- [ ] **Step 3: `desktop/web/src/components/clips/clip-list.tsx`**

```tsx
"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type ClipSummary } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { connectEventStream } from "@/lib/ws";
import type { AnalyzeEvent, AnalyzeProgress } from "@/lib/events";
import { ClipCard } from "./clip-card";
import { AnalyzeButton } from "./analyze-button";

export function ClipsTab({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.clips(projectId),
    queryFn: () => api.listClips(projectId),
  });
  const [progress, setProgress] = useState<Record<string, AnalyzeProgress>>({});

  useEffect(() => {
    const disconnect = connectEventStream(projectId, (evt: AnalyzeEvent) => {
      if (evt.type === "analyze.progress") {
        setProgress((p) => ({ ...p, [evt.clip_filename]: evt }));
      } else if (evt.type === "analyze.clip_done") {
        setProgress((p) => {
          const { [evt.clip_filename]: _, ...rest } = p;
          return rest;
        });
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      } else if (evt.type === "analyze.clip_failed") {
        // TODO: surface failures with a red badge + retry
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      } else if (evt.type === "analyze.complete") {
        setProgress({});
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      }
    });
    return disconnect;
  }, [projectId, qc]);

  if (isLoading) return <p className="text-[var(--color-muted)]">Loading clips…</p>;
  if (error) return <p className="text-red-600">Error: {String(error)}</p>;
  if (!data || data.length === 0) {
    return (
      <p className="text-[var(--color-muted)] py-12 text-center">
        No clips in this folder.
      </p>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-[var(--color-muted)]">{data.length} clips</p>
        <AnalyzeButton projectId={projectId} />
      </div>
      <div className="grid gap-3">
        {data.map((c) => (
          <ClipCard
            key={c.filename}
            clip={c}
            progress={progress[c.filename]}
          />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: `desktop/web/src/components/clips/analyze-button.tsx`**

```tsx
"use client";

import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function AnalyzeButton({ projectId }: { projectId: string }) {
  const mutation = useMutation({
    mutationFn: () => api.startAnalyze(projectId),
  });
  return (
    <button
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending}
      className="px-3 py-1.5 rounded-[4px] font-semibold text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60 text-sm transition"
    >
      {mutation.isPending ? "Starting…" : "Analyze"}
    </button>
  );
}
```

- [ ] **Step 5: Wire `onOpen` in `project-list.tsx`**

Edit `desktop/web/src/components/projects/project-list.tsx`. Replace the `onOpen={(id) => console.log("open project", id)}` line with a real navigation:

```tsx
"use client";

import { useRouter } from "next/navigation";
// ...
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
// ...
export function ProjectList() {
  const router = useRouter();
  // ...
  return (
    <div className="grid gap-3">
      {data.map((p) => (
        <ProjectCard
          key={p.id}
          project={p}
          onOpen={(id) => router.push(`/project?id=${id}&tab=clips`)}
          onForget={(id) => forget.mutate(id)}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Extend `query-keys.ts`**

Already has `clips(projectId)` from Plan 2 Task 4 — no change needed unless missing. Verify.

- [ ] **Step 7: Typecheck + build**

```bash
cd desktop/web
npx tsc --noEmit
npm run build
```

Both should succeed. Next.js static export will produce `/project.html` and `/index.html` since we used a query param instead of a dynamic segment.

- [ ] **Step 8: Commit**

```bash
git add desktop/web/src/app/project desktop/web/src/components/clips desktop/web/src/components/projects/project-list.tsx
git commit -m "feat(desktop): clips page with live analyze progress"
```

---

## Task 6: Verification + review doc

**Files:**
- Create: `docs/superpowers/plans/2026-04-17-plan-3-review.md`

- [ ] **Step 1: Full backend suite**

`.venv/bin/pytest -v` → expect **66 passed** (56 + 10 from this plan).

- [ ] **Step 2: Desktop typecheck + build**

```bash
cd desktop && npm run build
```

Expect successful builds in both workspaces.

- [ ] **Step 3: Smoke launch**

Follow Plan 2's smoke pattern. With `VLOGKIT_PYTHON=.venv/bin/python npm run dev` in one terminal, manually:

1. Window opens, empty project list (if no projects registered).
2. Click "Open folder" → pick a folder with some `.mp4` / `.mov` files → card appears.
3. Click the card → navigates to `/project?id=…&tab=clips`.
4. Clips listed as "unanalyzed" cards.
5. Click "Analyze" → per-clip progress bars animate as ffmpeg/whisper churn.
6. When done, cards flip to "analyzed" status with no progress bar.
7. Cmd-R reloads — still shows "analyzed" (persisted via `.vlogkit/clips/*.json`).

Note: a real analyze on a big file takes minutes. Recommend smoke with tiny clips (few seconds each). If you have none, point at the `/tmp/vlogkit-demo-clips` folder from earlier smoke tests — analyze will produce garbage output but the event flow will validate.

- [ ] **Step 4: Write Plan 3 review**

Template: as in Plans 1 and 2. Include:
- Commits from `git log <plan-2-last-sha>..HEAD`
- Rough edges (mention the `/media` auth-via-URL unresolved issue that Plan 4 needs to tackle for `<video>` playback)
- Deferred items for Plan 4 (storyboard editor, clip preview with auth)
- Any pipeline stages that don't emit per-clip progress (monkeypatch-friendly)

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-04-17-plan-3-review.md
git commit -m "docs: plan 3 review + carry-over items"
```

---

## Self-Review Notes

- Task 1 fixes Plan 1's `/media` linear scan — carry-over closed.
- Task 2/3 introduce the full event pipeline; the monkey-patched test keeps CI fast while the real pipeline still works in prod.
- Task 4's `getMediaUrl` was deleted from scope because token-in-URL is unsafe for general HTTP and solving it properly belongs in Plan 4 (along with `<video>` player).
- Task 5 uses a query-param route instead of `/project/[id]` because Next.js static export doesn't support dynamic segments without `generateStaticParams`, and for a single-user desktop app query-params are fine.
- Every step has real code or commands — no handwave.
