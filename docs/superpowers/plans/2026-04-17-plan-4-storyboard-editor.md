# Desktop App — Plan 4: Storyboard Editor (Hero View) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the storyboard editor — the hero UX of the whole app. Users see an LLM-generated timeline of sections + segments built from their analyzed clips, can reorder segments via drag-and-drop, retitle them in an inspector drawer, preview clips inline, and regenerate the storyboard with a streaming LLM response.

**Architecture:** Backend reuses `vlogkit.storyboard.builder.build_storyboard` for the LLM call, wraps it in a job runner that emits `storyboard.regen_token` events for live text. Storyboard is persisted to `.vlogkit/storyboard.json` per project (existing `vlogkit.project.save_storyboard` / `load_storyboard`). `/media/{hash}` accepts `?token=<bearer>` query param in addition to header auth — pragmatic for `<video src>` on a 127.0.0.1-bound server. Frontend adds a `board` tab driven by dnd-kit, with an inspector drawer, an inline `<video>` preview, and a streaming-regenerate button.

**Tech Stack:** Existing stack + `@dnd-kit/core`, `@dnd-kit/sortable`. No new backend deps — reuses existing `anthropic` + pipeline.

---

## File Structure

**Backend:**
- Modify: `src/vlogkit/server/auth.py` — add `require_token_or_query` dependency (accepts `?token=`)
- Modify: `src/vlogkit/server/routes/clips.py` — `/media/{hash}` uses the new dep
- Create: `src/vlogkit/server/routes/storyboard.py`
- Modify: `src/vlogkit/server/jobs.py` — add `run_regenerate_job`
- Modify: `src/vlogkit/server/schemas.py` — add `StoryboardRegenStarted/Token/Complete` events + response models
- Modify: `src/vlogkit/server/app.py` — mount storyboard routes
- Add: `tests/server/test_storyboard.py`, `tests/server/test_media_query_auth.py`

**Frontend:**
- Modify: `desktop/web/src/lib/api.ts` — add `getStoryboard`, `putStoryboard`, `regenerateStoryboard`, `getMediaUrl`
- Modify: `desktop/web/src/lib/events.ts` — extend `BoardEvent` union
- Create: `desktop/web/src/components/board/board.tsx` — tab root
- Create: `desktop/web/src/components/board/section-row.tsx`
- Create: `desktop/web/src/components/board/segment-block.tsx`
- Create: `desktop/web/src/components/board/inspector-drawer.tsx`
- Create: `desktop/web/src/components/board/regenerate-button.tsx`
- Create: `desktop/web/src/components/board/clip-preview.tsx`
- Create: `desktop/web/src/components/board/empty-board.tsx`
- Modify: `desktop/web/src/app/project/page.tsx` — mount `<Board>` on the board tab
- Install: `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`

---

## Task 0: Media auth-via-query for `<video>` playback

`<video src="...">` can't carry an Authorization header. Options considered: blob URLs (buffers to RAM), cookies (fiddly), signed short-lived tokens (overkill for 127.0.0.1). **Accepted trade:** allow `?token=<bearer>` as an alternative to the `Authorization: Bearer` header, but ONLY for the `/media/*` routes. The bearer token is per-process and never leaves the Electron window — on localhost this is fine.

**Files:**
- Modify: `src/vlogkit/server/auth.py`
- Modify: `src/vlogkit/server/routes/clips.py`
- Create: `tests/server/test_media_query_auth.py`

- [ ] **Step 1: Add `require_token_or_query` dep**

Append to `src/vlogkit/server/auth.py`:

```python
from fastapi import HTTPException, Query, Request


async def require_token_or_query(
    request: Request,
    authorization: str | None = Header(None),
    token: str | None = Query(None),
) -> None:
    """Accepts Bearer header OR ?token=<t> query param. For /media routes only."""
    expected = request.app.state.token
    # Try header first
    if authorization and authorization.startswith("Bearer "):
        supplied = authorization.removeprefix("Bearer ").strip()
        if supplied == expected:
            return
    # Fall back to query param
    if token == expected:
        return
    raise HTTPException(status_code=401, detail="invalid_token")
```

Keep the existing `require_token` untouched.

- [ ] **Step 2: Switch `/media/{hash}` to the new dep**

Edit `src/vlogkit/server/routes/clips.py::create_media_router`. Replace `dependencies=[Depends(require_token)]` with `dependencies=[Depends(require_token_or_query)]`. Import `require_token_or_query` alongside the existing `require_token`.

- [ ] **Step 3: Write failing tests**

Create `tests/server/test_media_query_auth.py`:

```python
"""Tests for /media/{hash} accepting ?token= query param."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


FAKE = b"VIDEO" * 200


@pytest.fixture
def seeded(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> tuple[str, str]:
    folder = tmp_path / "vlog"
    folder.mkdir()
    (folder / "clip.mp4").write_bytes(FAKE)
    h = hashlib.sha256(FAKE).hexdigest()
    desktop_client.post(
        "/projects", headers=auth_headers, json={"path": str(folder)}
    )
    return h, h[:16]


def test_media_accepts_query_token(
    desktop_client: TestClient, test_token: str, seeded: tuple[str, str]
) -> None:
    h, _ = seeded
    resp = desktop_client.get(f"/media/{h}?token={test_token}")
    assert resp.status_code == 200
    assert resp.content == FAKE


def test_media_query_accepts_16_char_prefix(
    desktop_client: TestClient, test_token: str, seeded: tuple[str, str]
) -> None:
    _, short = seeded
    resp = desktop_client.get(f"/media/{short}?token={test_token}")
    assert resp.status_code == 200


def test_media_header_auth_still_works(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    seeded: tuple[str, str],
) -> None:
    h, _ = seeded
    resp = desktop_client.get(f"/media/{h}", headers=auth_headers)
    assert resp.status_code == 200


def test_media_rejects_wrong_query_token(
    desktop_client: TestClient, seeded: tuple[str, str]
) -> None:
    h, _ = seeded
    resp = desktop_client.get(f"/media/{h}?token=wrong")
    assert resp.status_code == 401
```

Run `.venv/bin/pytest tests/server/test_media_query_auth.py -v` → FAIL first if tests run before Step 2, else PASS.

- [ ] **Step 4: Regenerate OpenAPI snapshot**

`VLOGKIT_UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/server/test_openapi_snapshot.py -v`

- [ ] **Step 5: Full suite**

`.venv/bin/pytest -v` → expect **73 passed** (69 + 4).

- [ ] **Step 6: Commit**

```bash
git add src/vlogkit/server/auth.py src/vlogkit/server/routes/clips.py tests/server/test_media_query_auth.py tests/server/snapshots/openapi.json
git commit -m "feat(server): /media/{hash} accepts ?token= query param for <video> playback"
```

---

## Task 1: Storyboard CRUD routes (`GET/PUT`)

**Files:**
- Create: `src/vlogkit/server/routes/storyboard.py`
- Modify: `src/vlogkit/server/app.py` — register router
- Create: `tests/server/test_storyboard.py`

Storyboard persistence already exists in `vlogkit.project` — `Project.save_storyboard(storyboard)` and `Project.load_storyboard() -> Storyboard | None`. The `Storyboard` model is in `vlogkit.models`.

- [ ] **Step 1: Write failing tests**

Create `tests/server/test_storyboard.py`:

```python
"""Tests for /projects/{id}/storyboard."""
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


def test_get_storyboard_empty_before_generation(
    desktop_client: TestClient, auth_headers: dict[str, str], registered: str
) -> None:
    resp = desktop_client.get(
        f"/projects/{registered}/storyboard", headers=auth_headers
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "storyboard_not_found"


def test_put_storyboard_roundtrips(
    desktop_client: TestClient, auth_headers: dict[str, str], registered: str
) -> None:
    body = {
        "title": "Weekend Trip",
        "sections": [
            {
                "title": "Intro",
                "segments": [
                    {
                        "title": "Opening shot",
                        "clip_filename": "a.mp4",
                        "start": 0.0,
                        "end": 2.5,
                    }
                ],
            }
        ],
    }
    resp = desktop_client.put(
        f"/projects/{registered}/storyboard",
        headers=auth_headers,
        json=body,
    )
    assert resp.status_code == 200, resp.text
    got = desktop_client.get(
        f"/projects/{registered}/storyboard", headers=auth_headers
    ).json()
    assert got["title"] == "Weekend Trip"
    assert got["sections"][0]["title"] == "Intro"


def test_put_storyboard_unknown_project_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.put(
        "/projects/deadbeefdeadbeef/storyboard",
        headers=auth_headers,
        json={"title": "x", "sections": []},
    )
    assert resp.status_code == 404


def test_storyboard_requires_auth(
    desktop_client: TestClient, registered: str
) -> None:
    assert (
        desktop_client.get(f"/projects/{registered}/storyboard").status_code
        == 401
    )
    assert (
        desktop_client.put(
            f"/projects/{registered}/storyboard", json={"sections": []}
        ).status_code
        == 401
    )
```

- [ ] **Step 2: Implement `storyboard.py` router**

Create `src/vlogkit/server/routes/storyboard.py`:

```python
"""/projects/{id}/storyboard CRUD."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from vlogkit.models import Storyboard
from vlogkit.project import Project
from vlogkit.server.auth import require_token
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail


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


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["storyboard"],
        dependencies=[Depends(require_token)],
    )

    @router.get(
        "/storyboard",
        response_model=Storyboard,
        responses={404: {"model": ErrorDetail}},
    )
    def get_storyboard(
        project_id: str,
        registry: ProjectRegistry = Depends(_registry),
    ) -> Storyboard:
        project = _load_project(registry, project_id)
        sb = project.load_storyboard()
        if sb is None:
            raise HTTPException(
                status_code=404,
                detail=ErrorDetail(
                    code="storyboard_not_found",
                    message="No storyboard generated for this project yet",
                ).model_dump(),
            )
        return sb

    @router.put(
        "/storyboard",
        response_model=Storyboard,
        responses={404: {"model": ErrorDetail}},
    )
    def put_storyboard(
        project_id: str,
        storyboard: Storyboard,
        registry: ProjectRegistry = Depends(_registry),
    ) -> Storyboard:
        project = _load_project(registry, project_id)
        project.save_storyboard(storyboard)
        return storyboard

    return router
```

Note: If `Project.load_storyboard` / `save_storyboard` don't exist under those names, read `src/vlogkit/project.py` first and use whatever exists. If the methods are missing entirely, report BLOCKED — the Storyboard model + persistence must already exist because the CLI `vlogkit storyboard` and `vlogkit review` commands use it.

- [ ] **Step 3: Mount in `create_desktop_app`**

In `src/vlogkit/server/app.py`:

```python
from vlogkit.server.routes import storyboard as storyboard_routes
# ...
app.include_router(storyboard_routes.create_router())
```

- [ ] **Step 4: Regenerate OpenAPI snapshot, run tests**

```
VLOGKIT_UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/server/test_openapi_snapshot.py -v
.venv/bin/pytest -v
```

Expect **77 passed** (73 + 4).

- [ ] **Step 5: Commit**

```bash
git add src/vlogkit/server/routes/storyboard.py src/vlogkit/server/app.py tests/server/test_storyboard.py tests/server/snapshots/openapi.json
git commit -m "feat(server): add /projects/{id}/storyboard GET/PUT"
```

---

## Task 2: Storyboard regenerate job + WS events

**Files:**
- Modify: `src/vlogkit/server/schemas.py` — add regen event models
- Modify: `src/vlogkit/server/jobs.py` — add `run_regenerate_job`
- Modify: `src/vlogkit/server/routes/storyboard.py` — add `POST /regenerate`
- Modify: `tests/server/test_storyboard.py` — add regen tests

- [ ] **Step 1: Add event schemas**

Append to `src/vlogkit/server/schemas.py`:

```python
class StoryboardRegenStarted(BaseModel):
    type: Literal["storyboard.regen_started"] = "storyboard.regen_started"
    job_id: str


class StoryboardRegenToken(BaseModel):
    type: Literal["storyboard.regen_token"] = "storyboard.regen_token"
    token: str


class StoryboardRegenComplete(BaseModel):
    type: Literal["storyboard.regen_complete"] = "storyboard.regen_complete"
    job_id: str
    storyboard: dict  # serialized Storyboard


class StoryboardRegenFailed(BaseModel):
    type: Literal["storyboard.regen_failed"] = "storyboard.regen_failed"
    job_id: str
    error: str
```

Extend `AnalyzeEvent` to include these (or rename the union to `BoardEvent`):

```python
BoardEvent = Union[
    AnalyzeStarted,
    AnalyzeProgress,
    AnalyzeClipDone,
    AnalyzeClipFailed,
    AnalyzeComplete,
    StoryboardRegenStarted,
    StoryboardRegenToken,
    StoryboardRegenComplete,
    StoryboardRegenFailed,
]

# Keep AnalyzeEvent for back-compat:
AnalyzeEvent = BoardEvent
```

- [ ] **Step 2: Add `run_regenerate_job` to `jobs.py`**

```python
# In src/vlogkit/server/jobs.py, after run_analyze_job:

async def run_regenerate_job(
    broker: "WsBroker",
    project_id: str,
    project: Project,
    job_id: str,
    strategy: str = "chronological",
    context: str = "",
) -> None:
    from vlogkit.server.schemas import (
        StoryboardRegenStarted,
        StoryboardRegenComplete,
        StoryboardRegenFailed,
    )
    await broker.publish(
        project_id, StoryboardRegenStarted(job_id=job_id)
    )
    try:
        # Reuse the existing builder — sync for now, run in thread.
        import asyncio
        from vlogkit.storyboard.builder import build_storyboard

        # Load all analyses from cache
        analyses = project.load_all_analyses()
        sb = await asyncio.to_thread(
            build_storyboard,
            analyses=analyses,
            settings=project.settings,
            strategy=strategy,
            context=context,
        )
        await asyncio.to_thread(project.save_storyboard, sb)
        await broker.publish(
            project_id,
            StoryboardRegenComplete(
                job_id=job_id,
                storyboard=sb.model_dump(mode="json"),
            ),
        )
    except Exception as exc:
        await broker.publish(
            project_id,
            StoryboardRegenFailed(job_id=job_id, error=str(exc)),
        )
```

Adjust function names for `load_all_analyses` and `build_storyboard` to whatever actually exists — read the modules first.

**Streaming-token events** are deferred: the existing `build_storyboard` returns a final `Storyboard`, not a token stream. Wiring real token streaming requires modifying the builder to accept a callback or switch to `anthropic`'s streaming API. For this plan we only emit `regen_started` → (wait) → `regen_complete`. The schema still includes `StoryboardRegenToken` so Plan 4.5 or later can wire it without a contract break.

- [ ] **Step 3: Add POST `/regenerate` route**

In `src/vlogkit/server/routes/storyboard.py`:

```python
import asyncio
import threading

from vlogkit.server.jobs import new_job_id, run_regenerate_job
from vlogkit.server.ws import WsBroker


def _broker(request: Request) -> WsBroker:
    return request.app.state.ws_broker


# Inside create_router, after the PUT route:
@router.post(
    "/storyboard/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: {"model": ErrorDetail}},
)
def regenerate(
    project_id: str,
    registry: ProjectRegistry = Depends(_registry),
    broker: WsBroker = Depends(_broker),
    request: Request = None,  # required for app.state access
) -> dict[str, str]:
    project = _load_project(registry, project_id)
    job_id = new_job_id()

    def run_in_thread():
        asyncio.run(run_regenerate_job(broker, project_id, project, job_id))

    threading.Thread(target=run_in_thread, daemon=True).start()
    return {"job_id": job_id}
```

Use the same threaded-job pattern as analyze (from Plan 3 Task 3) to avoid the TestClient event-loop trap.

- [ ] **Step 4: Write regen tests**

Append to `tests/server/test_storyboard.py`:

```python
def test_post_regenerate_starts_job(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vlogkit.server import jobs

    async def fake_run(broker, project_id, project, job_id, **kwargs):
        from vlogkit.server.schemas import (
            StoryboardRegenStarted,
            StoryboardRegenComplete,
        )
        await broker.publish(project_id, StoryboardRegenStarted(job_id=job_id))
        await broker.publish(
            project_id,
            StoryboardRegenComplete(
                job_id=job_id,
                storyboard={"title": "Stubbed", "sections": []},
            ),
        )

    monkeypatch.setattr(jobs, "run_regenerate_job", fake_run)

    resp = desktop_client.post(
        f"/projects/{registered}/storyboard/regenerate",
        headers=auth_headers,
    )
    assert resp.status_code == 202
    assert "job_id" in resp.json()
```

- [ ] **Step 5: Regenerate OpenAPI snapshot**

```
VLOGKIT_UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/server/test_openapi_snapshot.py -v
```

- [ ] **Step 6: Full suite**

`.venv/bin/pytest -v` → expect **78 passed** (77 + 1).

- [ ] **Step 7: Commit**

```bash
git add src/vlogkit/server/schemas.py src/vlogkit/server/jobs.py src/vlogkit/server/routes/storyboard.py tests/server/test_storyboard.py tests/server/snapshots/openapi.json
git commit -m "feat(server): storyboard /regenerate with WS events"
```

---

## Task 3: Frontend API + event types + deps

**Files:**
- Regenerate: `desktop/web/src/lib/api-types.ts`
- Modify: `desktop/web/src/lib/api.ts`
- Modify: `desktop/web/src/lib/events.ts`
- Modify: `desktop/web/package.json` — add `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`

- [ ] **Step 1: Regen API types**

```bash
cd /Users/bryan/Code/lsl/vlogkit
bash desktop/scripts/gen-api-types.sh
```

Verify `Storyboard`, `StoryboardSection`, `StoryboardSegment` appear in `components/schemas`. If not (they'd only land because of `response_model=Storyboard` on the GET/PUT routes we added), flag BLOCKED.

- [ ] **Step 2: Install dnd-kit**

```bash
cd desktop/web
npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities
```

- [ ] **Step 3: Extend `lib/api.ts`**

Add to the `api` object:

```typescript
getStoryboard: (projectId: string) =>
  request<Storyboard>(`/projects/${projectId}/storyboard`),
putStoryboard: (projectId: string, storyboard: Storyboard) =>
  request<Storyboard>(`/projects/${projectId}/storyboard`, {
    method: "PUT",
    body: JSON.stringify(storyboard),
  }),
regenerateStoryboard: (projectId: string) =>
  request<{ job_id: string }>(
    `/projects/${projectId}/storyboard/regenerate`,
    { method: "POST" },
  ),
```

At the bottom of the file, add:

```typescript
export function getMediaUrl(hash: string): string {
  const { apiPort, token } = getBridge();
  return `http://127.0.0.1:${apiPort}/media/${hash}?token=${encodeURIComponent(token)}`;
}

export type Storyboard = components["schemas"]["Storyboard"];
export type StoryboardSection = components["schemas"]["StoryboardSection"];
export type StoryboardSegment = components["schemas"]["StoryboardSegment"];
```

If the generated types don't have exactly those schema names, use whatever is actually generated — read the file.

- [ ] **Step 4: Extend `lib/events.ts`**

Add:

```typescript
export type StoryboardRegenStarted = {
  type: "storyboard.regen_started";
  job_id: string;
};
export type StoryboardRegenToken = {
  type: "storyboard.regen_token";
  token: string;
};
export type StoryboardRegenComplete = {
  type: "storyboard.regen_complete";
  job_id: string;
  storyboard: unknown;
};
export type StoryboardRegenFailed = {
  type: "storyboard.regen_failed";
  job_id: string;
  error: string;
};

export type BoardEvent =
  | AnalyzeEvent
  | StoryboardRegenStarted
  | StoryboardRegenToken
  | StoryboardRegenComplete
  | StoryboardRegenFailed;
```

Keep `AnalyzeEvent` export as-is.

- [ ] **Step 5: Typecheck + build**

```bash
cd desktop/web
npx tsc --noEmit
npm run build
```

- [ ] **Step 6: Commit**

```bash
git add desktop/web/src/lib desktop/web/package.json desktop/web/package-lock.json desktop/package-lock.json
git commit -m "feat(desktop): storyboard + dnd-kit deps + API types"
```

---

## Task 4: Board tab — read-only timeline

First MVP of the board: reads the storyboard, renders sections as rows with segment blocks. No editing yet — that's Task 5. No preview — that's Task 6.

**Files:**
- Create: `desktop/web/src/components/board/board.tsx`
- Create: `desktop/web/src/components/board/section-row.tsx`
- Create: `desktop/web/src/components/board/segment-block.tsx`
- Create: `desktop/web/src/components/board/empty-board.tsx`
- Modify: `desktop/web/src/app/project/page.tsx` — mount `<Board>` on the board tab

- [ ] **Step 1: `empty-board.tsx`**

```tsx
import { api } from "@/lib/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";

export function EmptyBoard({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: () => api.regenerateStoryboard(projectId),
    onSuccess: () => qc.invalidateQueries(),
  });
  return (
    <div className="text-center py-24 px-8">
      <h2 className="text-2xl font-bold mb-3">No storyboard yet</h2>
      <p className="text-[var(--color-muted)] max-w-md mx-auto mb-6">
        Once your clips are analyzed, generate a storyboard and arrange the
        sequence the way you want.
      </p>
      <button
        onClick={() => mut.mutate()}
        disabled={mut.isPending}
        className="px-4 py-2 rounded-[4px] font-semibold text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60"
      >
        {mut.isPending ? "Generating…" : "Generate storyboard"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: `segment-block.tsx`**

```tsx
import type { StoryboardSegment } from "@/lib/api";

export function SegmentBlock({
  segment,
  selected,
  onSelect,
}: {
  segment: StoryboardSegment;
  selected: boolean;
  onSelect: () => void;
}) {
  const duration = segment.end - segment.start;
  return (
    <button
      onClick={onSelect}
      className={
        "text-left bg-white rounded-[8px] border p-3 min-w-[200px] transition " +
        (selected
          ? "border-[var(--color-accent)] ring-1 ring-[var(--color-accent-focus)]"
          : "border-[var(--color-border-whisper)] hover:border-[var(--color-muted)]")
      }
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="font-semibold text-sm truncate">{segment.title}</div>
      <div className="text-xs text-[var(--color-muted)] truncate mt-1">
        {segment.clip_filename}
      </div>
      <div className="text-xs text-[var(--color-placeholder)] mt-1">
        {segment.start.toFixed(1)}s → {segment.end.toFixed(1)}s
        ({duration.toFixed(1)}s)
      </div>
    </button>
  );
}
```

- [ ] **Step 3: `section-row.tsx`**

```tsx
import type { StoryboardSection, StoryboardSegment } from "@/lib/api";
import { SegmentBlock } from "./segment-block";

export function SectionRow({
  section,
  selectedSegmentKey,
  onSelectSegment,
}: {
  section: StoryboardSection;
  selectedSegmentKey: string | null;
  onSelectSegment: (key: string, segment: StoryboardSegment) => void;
}) {
  return (
    <section className="border-t border-[var(--color-border-whisper)] pt-4 mt-4 first:border-t-0 first:mt-0 first:pt-0">
      <h3 className="mb-3">{section.title}</h3>
      <div className="flex gap-2 overflow-x-auto pb-2">
        {section.segments.map((seg, idx) => {
          const key = `${section.title}/${idx}`;
          return (
            <SegmentBlock
              key={key}
              segment={seg}
              selected={selectedSegmentKey === key}
              onSelect={() => onSelectSegment(key, seg)}
            />
          );
        })}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: `board.tsx`**

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type StoryboardSegment } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { SectionRow } from "./section-row";
import { EmptyBoard } from "./empty-board";

export function Board({ projectId }: { projectId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: [...queryKeys.project(projectId), "storyboard"],
    queryFn: () => api.getStoryboard(projectId),
    retry: false,
  });
  const [selected, setSelected] = useState<{
    key: string;
    segment: StoryboardSegment;
  } | null>(null);

  if (isLoading) {
    return <p className="text-[var(--color-muted)]">Loading storyboard…</p>;
  }
  // 404 means no storyboard yet — not a real error.
  if (error && String(error).includes("storyboard_not_found")) {
    return <EmptyBoard projectId={projectId} />;
  }
  if (error) {
    return <p className="text-red-600">Error: {String(error)}</p>;
  }
  if (!data) return <EmptyBoard projectId={projectId} />;

  return (
    <div className="grid grid-cols-[1fr_320px] gap-6">
      <div>
        {data.sections.map((s, i) => (
          <SectionRow
            key={i}
            section={s}
            selectedSegmentKey={selected?.key ?? null}
            onSelectSegment={(key, segment) => setSelected({ key, segment })}
          />
        ))}
      </div>
      <aside className="bg-[var(--color-background-alt)] rounded-[12px] p-4 h-fit sticky top-6">
        {selected ? (
          <>
            <h4 className="font-semibold mb-2">{selected.segment.title}</h4>
            <p className="text-sm text-[var(--color-muted)]">
              {selected.segment.clip_filename}
            </p>
            <p className="text-xs text-[var(--color-placeholder)] mt-2">
              Preview + editing coming in Tasks 5 and 6.
            </p>
          </>
        ) : (
          <p className="text-sm text-[var(--color-muted)]">
            Select a segment to inspect it.
          </p>
        )}
      </aside>
    </div>
  );
}
```

- [ ] **Step 5: Wire into `app/project/page.tsx`**

Replace the `{tab === "board" && <Placeholder name="Storyboard editor — Plan 4" />}` line with:

```tsx
{tab === "board" && <Board projectId={id} />}
```

And import `Board` at the top: `import { Board } from "@/components/board/board";`

- [ ] **Step 6: Typecheck + build**

```bash
cd desktop/web
npx tsc --noEmit && npm run build
```

- [ ] **Step 7: Commit**

```bash
git add desktop/web/src/components/board desktop/web/src/app/project/page.tsx
git commit -m "feat(desktop): board tab read-only timeline view"
```

---

## Task 5: Drag-to-reorder segments with dnd-kit

Enable dragging a segment within its own section to change its position. Cross-section drag + re-titling happens via the inspector drawer (Task 6).

**Files:**
- Modify: `desktop/web/src/components/board/board.tsx` — wrap in `<DndContext>` with `sensors`
- Modify: `desktop/web/src/components/board/section-row.tsx` — wrap segments in `<SortableContext>`
- Modify: `desktop/web/src/components/board/segment-block.tsx` — use `useSortable`
- Create: `desktop/web/src/components/board/use-segment-reorder.ts` — mutation hook

- [ ] **Step 1: Create `use-segment-reorder.ts`**

```typescript
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type Storyboard } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

export function useSegmentReorder(projectId: string) {
  const qc = useQueryClient();
  const key = [...queryKeys.project(projectId), "storyboard"];

  return useMutation({
    mutationFn: async (sb: Storyboard) => api.putStoryboard(projectId, sb),
    onMutate: async (newSb) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<Storyboard>(key);
      qc.setQueryData(key, newSb);
      return { prev };
    },
    onError: (_err, _new, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key }),
  });
}
```

- [ ] **Step 2: Update `segment-block.tsx` to use `useSortable`**

```tsx
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { StoryboardSegment } from "@/lib/api";

export function SegmentBlock({
  id,
  segment,
  selected,
  onSelect,
}: {
  id: string;
  segment: StoryboardSegment;
  selected: boolean;
  onSelect: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };
  const duration = segment.end - segment.start;
  return (
    <button
      ref={setNodeRef}
      onClick={onSelect}
      {...attributes}
      {...listeners}
      style={{ ...style, boxShadow: "var(--shadow-card)" }}
      className={
        "text-left bg-white rounded-[8px] border p-3 min-w-[200px] transition cursor-grab active:cursor-grabbing " +
        (selected
          ? "border-[var(--color-accent)] ring-1 ring-[var(--color-accent-focus)]"
          : "border-[var(--color-border-whisper)] hover:border-[var(--color-muted)]")
      }
    >
      <div className="font-semibold text-sm truncate">{segment.title}</div>
      <div className="text-xs text-[var(--color-muted)] truncate mt-1">
        {segment.clip_filename}
      </div>
      <div className="text-xs text-[var(--color-placeholder)] mt-1">
        {segment.start.toFixed(1)}s → {segment.end.toFixed(1)}s
        ({duration.toFixed(1)}s)
      </div>
    </button>
  );
}
```

- [ ] **Step 3: Update `section-row.tsx` to wrap in `<SortableContext>`**

```tsx
import { SortableContext, horizontalListSortingStrategy } from "@dnd-kit/sortable";
import type { StoryboardSection, StoryboardSegment } from "@/lib/api";
import { SegmentBlock } from "./segment-block";

export function SectionRow({
  sectionIndex,
  section,
  selectedSegmentKey,
  onSelectSegment,
}: {
  sectionIndex: number;
  section: StoryboardSection;
  selectedSegmentKey: string | null;
  onSelectSegment: (key: string, segment: StoryboardSegment) => void;
}) {
  const items = section.segments.map((_, idx) => `${sectionIndex}:${idx}`);
  return (
    <section className="border-t border-[var(--color-border-whisper)] pt-4 mt-4 first:border-t-0 first:mt-0 first:pt-0">
      <h3 className="mb-3">{section.title}</h3>
      <SortableContext items={items} strategy={horizontalListSortingStrategy}>
        <div className="flex gap-2 overflow-x-auto pb-2">
          {section.segments.map((seg, idx) => {
            const id = `${sectionIndex}:${idx}`;
            return (
              <SegmentBlock
                key={id}
                id={id}
                segment={seg}
                selected={selectedSegmentKey === id}
                onSelect={() => onSelectSegment(id, seg)}
              />
            );
          })}
        </div>
      </SortableContext>
    </section>
  );
}
```

- [ ] **Step 4: Update `board.tsx` to provide `<DndContext>` and handle `onDragEnd`**

Replace the existing body with one that:
1. Wraps children in `<DndContext sensors={...} onDragEnd={handleDragEnd}>`
2. On drag-end within the same section, splices the segment in its parent section's `segments` array.
3. Calls the reorder mutation with the new storyboard.

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { arrayMove } from "@dnd-kit/sortable";

import { api, type Storyboard, type StoryboardSegment } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { SectionRow } from "./section-row";
import { EmptyBoard } from "./empty-board";
import { useSegmentReorder } from "./use-segment-reorder";

export function Board({ projectId }: { projectId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: [...queryKeys.project(projectId), "storyboard"],
    queryFn: () => api.getStoryboard(projectId),
    retry: false,
  });
  const reorder = useSegmentReorder(projectId);
  const [selected, setSelected] = useState<{
    key: string;
    segment: StoryboardSegment;
  } | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  function handleDragEnd(evt: DragEndEvent) {
    const { active, over } = evt;
    if (!over || !data || active.id === over.id) return;
    const [fromSec, fromIdx] = String(active.id).split(":").map(Number);
    const [toSec, toIdx] = String(over.id).split(":").map(Number);
    if (fromSec !== toSec) return; // cross-section reorder not handled yet
    const next: Storyboard = JSON.parse(JSON.stringify(data));
    next.sections[fromSec].segments = arrayMove(
      next.sections[fromSec].segments,
      fromIdx,
      toIdx,
    );
    reorder.mutate(next);
  }

  if (isLoading)
    return <p className="text-[var(--color-muted)]">Loading storyboard…</p>;
  if (error && String(error).includes("storyboard_not_found"))
    return <EmptyBoard projectId={projectId} />;
  if (error) return <p className="text-red-600">Error: {String(error)}</p>;
  if (!data) return <EmptyBoard projectId={projectId} />;

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <div className="grid grid-cols-[1fr_320px] gap-6">
        <div>
          {data.sections.map((s, i) => (
            <SectionRow
              key={i}
              sectionIndex={i}
              section={s}
              selectedSegmentKey={selected?.key ?? null}
              onSelectSegment={(key, segment) =>
                setSelected({ key, segment })
              }
            />
          ))}
        </div>
        <aside className="bg-[var(--color-background-alt)] rounded-[12px] p-4 h-fit sticky top-6">
          {selected ? (
            <>
              <h4 className="font-semibold mb-2">{selected.segment.title}</h4>
              <p className="text-sm text-[var(--color-muted)]">
                {selected.segment.clip_filename}
              </p>
              <p className="text-xs text-[var(--color-placeholder)] mt-2">
                Preview + editing coming in Task 6.
              </p>
            </>
          ) : (
            <p className="text-sm text-[var(--color-muted)]">
              Select a segment to inspect it.
            </p>
          )}
        </aside>
      </div>
    </DndContext>
  );
}
```

- [ ] **Step 5: Typecheck + build**

```bash
cd desktop/web
npx tsc --noEmit && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add desktop/web/src/components/board
git commit -m "feat(desktop): dnd-kit intra-section segment reorder"
```

---

## Task 6: Inspector drawer + clip preview

Replace the aside placeholder with a real inspector: editable title, editable start/end times, and a `<video>` preview that scrubs to the segment's in/out times.

**Files:**
- Create: `desktop/web/src/components/board/inspector-drawer.tsx`
- Create: `desktop/web/src/components/board/clip-preview.tsx`
- Modify: `desktop/web/src/components/board/board.tsx` — use the new inspector

- [ ] **Step 1: `clip-preview.tsx`**

```tsx
"use client";

import { useEffect, useRef } from "react";
import { getMediaUrl } from "@/lib/api";

export function ClipPreview({
  clipSha256,
  start,
  end,
}: {
  clipSha256: string | null | undefined;
  start: number;
  end: number;
}) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    // Jump to start whenever the segment changes
    const onLoaded = () => {
      v.currentTime = start;
    };
    v.addEventListener("loadedmetadata", onLoaded);
    return () => v.removeEventListener("loadedmetadata", onLoaded);
  }, [start, clipSha256]);

  if (!clipSha256) {
    return (
      <div className="aspect-video bg-[var(--color-background-alt)] rounded-[8px] flex items-center justify-center text-sm text-[var(--color-muted)]">
        Clip not analyzed yet — no preview available
      </div>
    );
  }

  return (
    <video
      ref={ref}
      src={getMediaUrl(clipSha256)}
      controls
      className="w-full rounded-[8px] border border-[var(--color-border-whisper)]"
      onTimeUpdate={(e) => {
        const v = e.currentTarget;
        if (v.currentTime > end) v.pause();
      }}
    />
  );
}
```

`clipSha256` must be the 16-char prefix the backend emits — we need to resolve it. The segment model has `clip_filename`, not sha256. Approach: the Board should pass the matching clip's `sha256` looked up from `/clips`. Simplest way: Board fetches `/clips` alongside `/storyboard` and builds a `filename → sha256` map. Then when rendering the inspector, pass `map.get(segment.clip_filename)`.

- [ ] **Step 2: `inspector-drawer.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import type { StoryboardSegment, Storyboard } from "@/lib/api";
import { ClipPreview } from "./clip-preview";

export function InspectorDrawer({
  segment,
  sectionIndex,
  segmentIndex,
  storyboard,
  clipSha256,
  onSave,
}: {
  segment: StoryboardSegment;
  sectionIndex: number;
  segmentIndex: number;
  storyboard: Storyboard;
  clipSha256: string | null | undefined;
  onSave: (next: Storyboard) => void;
}) {
  const [title, setTitle] = useState(segment.title);
  const [start, setStart] = useState(segment.start);
  const [end, setEnd] = useState(segment.end);

  // Reset form when selection changes
  useEffect(() => {
    setTitle(segment.title);
    setStart(segment.start);
    setEnd(segment.end);
  }, [segment]);

  // Debounced save
  useEffect(() => {
    const handle = setTimeout(() => {
      if (
        title === segment.title &&
        start === segment.start &&
        end === segment.end
      ) return;
      const next: Storyboard = JSON.parse(JSON.stringify(storyboard));
      next.sections[sectionIndex].segments[segmentIndex] = {
        ...segment,
        title,
        start,
        end,
      };
      onSave(next);
    }, 500);
    return () => clearTimeout(handle);
  }, [title, start, end]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <ClipPreview clipSha256={clipSha256} start={start} end={end} />
      <label className="block">
        <span className="text-xs text-[var(--color-muted)]">Title</span>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="mt-1 w-full rounded-[4px] border border-[var(--color-border-whisper)] bg-white px-2 py-1 text-sm"
        />
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="text-xs text-[var(--color-muted)]">Start (s)</span>
          <input
            type="number"
            step="0.1"
            value={start}
            onChange={(e) => setStart(parseFloat(e.target.value) || 0)}
            className="mt-1 w-full rounded-[4px] border border-[var(--color-border-whisper)] bg-white px-2 py-1 text-sm"
          />
        </label>
        <label className="block">
          <span className="text-xs text-[var(--color-muted)]">End (s)</span>
          <input
            type="number"
            step="0.1"
            value={end}
            onChange={(e) => setEnd(parseFloat(e.target.value) || 0)}
            className="mt-1 w-full rounded-[4px] border border-[var(--color-border-whisper)] bg-white px-2 py-1 text-sm"
          />
        </label>
      </div>
      <p className="text-xs text-[var(--color-placeholder)]">
        {segment.clip_filename}
      </p>
    </div>
  );
}
```

- [ ] **Step 3: Update `board.tsx` to include clips fetch + pass to Inspector**

Add a `useQuery` for clips and build a sha256 map. Wire inspector:

```tsx
// ... inside Board, alongside the storyboard query:
const { data: clips } = useQuery({
  queryKey: queryKeys.clips(projectId),
  queryFn: () => api.listClips(projectId),
});
const hashMap = new Map<string, string>();
(clips ?? []).forEach((c) => {
  if (c.sha256) hashMap.set(c.filename, c.sha256);
});

// ... in the aside block, replace the placeholder content:
{selected && data ? (
  <InspectorDrawer
    segment={selected.segment}
    sectionIndex={Number(selected.key.split(":")[0])}
    segmentIndex={Number(selected.key.split(":")[1])}
    storyboard={data}
    clipSha256={hashMap.get(selected.segment.clip_filename)}
    onSave={(next) => reorder.mutate(next)}
  />
) : (
  <p className="text-sm text-[var(--color-muted)]">
    Select a segment to inspect it.
  </p>
)}
```

Import `InspectorDrawer` at the top.

- [ ] **Step 4: Typecheck + build**

```bash
cd desktop/web
npx tsc --noEmit && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add desktop/web/src/components/board
git commit -m "feat(desktop): inspector drawer with clip preview + edit"
```

---

## Task 7: Regenerate button + WS event wiring

Add a "Regenerate" button above the board that POSTs to `/regenerate` and listens for `storyboard.regen_complete` on the project WS stream.

**Files:**
- Create: `desktop/web/src/components/board/regenerate-button.tsx`
- Modify: `desktop/web/src/components/board/board.tsx` — mount the button + subscribe to WS

- [ ] **Step 1: `regenerate-button.tsx`**

```tsx
"use client";

import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function RegenerateButton({
  projectId,
  inFlight,
}: {
  projectId: string;
  inFlight: boolean;
}) {
  const mut = useMutation({
    mutationFn: () => api.regenerateStoryboard(projectId),
  });
  const running = mut.isPending || inFlight;
  return (
    <button
      onClick={() => mut.mutate()}
      disabled={running}
      className="px-3 py-1.5 rounded-[4px] font-semibold text-sm text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60 transition"
    >
      {running ? "Regenerating…" : "Regenerate"}
    </button>
  );
}
```

- [ ] **Step 2: Subscribe to WS in `board.tsx`**

Add at the top of Board (after other hooks):

```tsx
const qc = useQueryClient();
const [regenInFlight, setRegenInFlight] = useState(false);

useEffect(() => {
  const dc = connectEventStream(projectId, (evt) => {
    if (evt.type === "storyboard.regen_started") {
      setRegenInFlight(true);
    } else if (
      evt.type === "storyboard.regen_complete" ||
      evt.type === "storyboard.regen_failed"
    ) {
      setRegenInFlight(false);
      qc.invalidateQueries({
        queryKey: [...queryKeys.project(projectId), "storyboard"],
      });
    }
  });
  return dc;
}, [projectId, qc]);
```

Render the button in the header:

```tsx
<div className="flex items-center justify-between mb-4">
  <p className="text-sm text-[var(--color-muted)]">
    {data.sections.length} sections ·{" "}
    {data.sections.reduce((n, s) => n + s.segments.length, 0)} segments
  </p>
  <RegenerateButton projectId={projectId} inFlight={regenInFlight} />
</div>
```

Imports: `useQueryClient`, `useEffect`, `useState`, `connectEventStream`, `RegenerateButton`.

- [ ] **Step 3: Typecheck + build**

```bash
cd desktop/web
npx tsc --noEmit && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add desktop/web/src/components/board
git commit -m "feat(desktop): regenerate button + WS-driven storyboard refresh"
```

---

## Task 8: Verification + Plan 4 review

- [ ] **Step 1: Backend suite**

`.venv/bin/pytest -v` → expect **78 passed**.

- [ ] **Step 2: Desktop build + typecheck**

```bash
cd desktop && npm run build
```

- [ ] **Step 3: Manual smoke (documented)**

Launch: `cd desktop && VLOGKIT_PYTHON=/path/to/.venv/bin/python npm run dev`.

Walk through:
1. Open folder (real clips)
2. Analyze (Plan 3 flow) — wait for clips to flip to `analyzed`
3. Switch to the **board** tab — empty state "Generate storyboard"
4. Click Generate — button shows "Regenerating…", then after a few seconds (real LLM call), storyboard appears
5. Click a segment — inspector opens on the right, video preview loads, scrubs to segment start
6. Drag a segment within its section — it animates + persists via `/storyboard` PUT (check `.vlogkit/storyboard.json`)
7. Edit title in inspector → 500ms debounce → PUT persists
8. Switch to "clips" tab and back — storyboard state persists
9. Click Regenerate — new storyboard replaces old one

- [ ] **Step 4: Plan 4 review doc**

Create `docs/superpowers/plans/2026-04-17-plan-4-review.md` with the usual template:
- Commits from `git log <plan-3-last-sha>..HEAD`
- Shipped: query-auth for media, storyboard CRUD, regenerate, read-only board, dnd reorder, inspector + preview, WS regen wiring
- Rough edges:
  - `storyboard.regen_token` schema exists but never emitted (the LLM call doesn't stream yet — future Plan 4.5 could switch builder to `anthropic.messages.stream()`)
  - Cross-section segment drag not supported
  - No undo/redo
  - Clip preview uses full `<video>` element but no waveform / keyframe scrub yet
  - 404 error-detection via string-matching `"storyboard_not_found"` is fragile — improve with ApiError.code check
- Deferred for Plan 5 (search), Plan 6 (export + packaging)

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-04-17-plan-4-review.md
git commit -m "docs: plan 4 review + carry-over items"
```

---

## Self-Review Notes

- Task 0's query-param auth for `/media` is the least-bad option for `<video src>` on a 127.0.0.1 sidecar. Token is already per-process, never written to disk; leak via browser history is moot in Electron.
- Tasks 2's `StoryboardRegenToken` event is schema-ready but never emitted — `build_storyboard` doesn't stream. Forward-compat for when we wire `anthropic`'s streaming API.
- Task 5's cross-section drag was explicitly deferred because dnd-kit's `DragOverEvent` needs more logic (tracking `containerId`) and this plan is already large. Plan 4.5 or a follow-up can add it.
- Task 6 hard-wires the segment↔clip relationship via filename. A follow-up could move to clip_hash for robustness but filename works today.
- Every step has real code — no placeholders.
