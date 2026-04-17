# Desktop App — Plan 5: Semantic Search Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the third main tab — semantic clip search. User types "sunset over bridge" and sees thumbnails of matching clip segments. Drag a result onto the board to insert it as a new segment.

**Architecture:** Backend wraps the existing `vlogkit.search` module (`[search]` optional extra — sentrysearch + chromadb + google-genai). New `/projects/{id}/search` routes: `POST /index` to build/refresh the per-project Chroma index, `GET /?q=...` for queries. Graceful degradation when `[search]` deps aren't installed — return a 503 with a helpful message. No WS events in this plan — indexing streams via HTTP progress-polling. Also lands the Plan 4 carry-over: extract shared `_registry` + `_load_project` helpers into `server/deps.py`.

**Tech Stack:** Existing stack + graceful import guard for `vlogkit.search`. Frontend uses existing dnd-kit for drop-into-board.

---

## File Structure

**Backend:**
- Create: `src/vlogkit/server/deps.py` — shared dependency helpers (`get_registry`, `load_project`, `get_broker`)
- Modify: `src/vlogkit/server/routes/*.py` — import helpers from `deps.py` instead of duplicating
- Create: `src/vlogkit/server/routes/search.py`
- Modify: `src/vlogkit/server/schemas.py` — add `SearchHit`, `IndexStatus` response models
- Modify: `src/vlogkit/server/app.py` — register search router
- Add: `tests/server/test_search.py`, `tests/server/test_deps.py`

**Frontend:**
- Modify: `desktop/web/src/lib/api.ts` — add `searchClips`, `buildSearchIndex`, `getIndexStatus`
- Create: `desktop/web/src/components/search/search-panel.tsx`
- Create: `desktop/web/src/components/search/search-bar.tsx`
- Create: `desktop/web/src/components/search/result-card.tsx`
- Create: `desktop/web/src/components/search/index-prompt.tsx`
- Modify: `desktop/web/src/app/project/page.tsx` — wire `<SearchPanel>` on the search tab
- Modify: `desktop/web/src/components/board/board.tsx` — accept drops from the search panel as a new segment
- Modify: `desktop/web/src/components/board/section-row.tsx` — droppable target

---

## Task 0: Extract shared deps to `server/deps.py`

Carry-over from Plan 4 review. `_registry` and `_load_project` are duplicated in 5 route files. Before adding a 6th (search), extract.

**Files:**
- Create: `src/vlogkit/server/deps.py`
- Modify: `src/vlogkit/server/routes/projects.py`, `.../clips.py`, `.../analyze.py`, `.../storyboard.py`
- Create: `tests/server/test_deps.py`

- [ ] **Step 1: Create `deps.py`**

```python
"""Shared FastAPI dependency helpers."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request

from vlogkit.project import Project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail
from vlogkit.server.ws import WsBroker


def get_registry(request: Request) -> ProjectRegistry:
    return request.app.state.registry


def get_broker(request: Request) -> WsBroker:
    return request.app.state.ws_broker


def load_project(registry: ProjectRegistry, project_id: str) -> Project:
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
```

- [ ] **Step 2: Write `test_deps.py`**

```python
"""Tests for shared dependency helpers."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from vlogkit.server.deps import load_project
from vlogkit.server.registry import ProjectRegistry


def test_load_project_returns_project(tmp_path: Path) -> None:
    folder = tmp_path / "proj"
    folder.mkdir()
    reg = ProjectRegistry(tmp_path / "projects.json")
    entry = reg.register(folder)
    project = load_project(reg, entry.id)
    assert project.root == folder


def test_load_project_raises_404_for_unknown(tmp_path: Path) -> None:
    reg = ProjectRegistry(tmp_path / "projects.json")
    with pytest.raises(HTTPException) as ei:
        load_project(reg, "not-a-real-id")
    assert ei.value.status_code == 404
    assert ei.value.detail["code"] == "project_not_found"
```

- [ ] **Step 3: Replace `_registry` / `_load_project` / `_broker` in each route file**

For each of these files:
- `src/vlogkit/server/routes/projects.py`
- `src/vlogkit/server/routes/clips.py`
- `src/vlogkit/server/routes/analyze.py`
- `src/vlogkit/server/routes/storyboard.py`

Delete the file-local `_registry`, `_load_project`, `_broker` functions. Replace their usage with imports from `deps.py`:

```python
from vlogkit.server.deps import get_registry, get_broker, load_project

# Any `Depends(_registry)` → `Depends(get_registry)`
# Any `Depends(_broker)` → `Depends(get_broker)`
# Any `_load_project(registry, pid)` → `load_project(registry, pid)`
```

Do NOT change function bodies beyond the rename.

- [ ] **Step 4: Full suite**

`.venv/bin/pytest -v` → expect **82 passed** (80 + 2 from `test_deps.py`).

- [ ] **Step 5: Commit**

```bash
git add src/vlogkit/server/deps.py src/vlogkit/server/routes/ tests/server/test_deps.py
git commit -m "refactor(server): extract shared registry/project/broker deps"
```

---

## Task 1: Backend search routes

`vlogkit.search` is the existing module from `[search]` extras. Expected surface (adapt to real names):
- `vlogkit.search.indexer.build_index(project: Project) -> None` — rebuilds the per-project Chroma index
- `vlogkit.search.query.search(project: Project, query: str, k: int = 10) -> list[SearchHit]`
- `vlogkit.search.query.index_stats(project: Project) -> dict` — e.g. `{indexed: int, total: int}`

**Pre-work:** Read `src/vlogkit/search/__init__.py`, `src/vlogkit/search/indexer.py`, `src/vlogkit/search/query.py`. Report:
- Actual function names + signatures
- What a search result looks like (a dict? a dataclass?) — we'll model `SearchHit` after that
- Whether indexing is sync-blocking (probably yes — it calls Gemini embedding API per chunk)

If `vlogkit.search` fails to import due to missing `[search]` extras on this dev machine, the routes must still load — just return 503s. Use a lazy import inside the route functions.

**Files:**
- Create: `src/vlogkit/server/routes/search.py`
- Modify: `src/vlogkit/server/schemas.py` — add search response models
- Modify: `src/vlogkit/server/app.py` — register router
- Create: `tests/server/test_search.py`

- [ ] **Step 1: Add response schemas**

Append to `src/vlogkit/server/schemas.py`:

```python
class SearchHit(BaseModel):
    clip_filename: str
    clip_sha256: str | None = None
    chunk_start: float  # seconds into clip
    chunk_end: float
    score: float  # 0..1, higher is more relevant
    snippet: str = ""  # optional text snippet (transcription excerpt, etc.)


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


class IndexStatus(BaseModel):
    indexed: int
    total: int
    ready: bool  # True when indexed >= total
```

- [ ] **Step 2: Write failing tests**

Create `tests/server/test_search.py`:

```python
"""Tests for /projects/{id}/search."""
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


def test_search_returns_hits(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vlogkit.server.routes import search as search_route

    def fake_search(project, query: str, k: int = 10):
        return [
            {
                "clip_filename": "a.mp4",
                "clip_sha256": "abc123def456" + "0" * 52,
                "chunk_start": 0.0,
                "chunk_end": 5.0,
                "score": 0.9,
                "snippet": "A bright sunset over the bridge",
            }
        ]

    monkeypatch.setattr(search_route, "_do_search", fake_search)

    resp = desktop_client.get(
        f"/projects/{registered}/search?q=sunset", headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"] == "sunset"
    assert len(body["hits"]) == 1
    assert body["hits"][0]["clip_filename"] == "a.mp4"


def test_search_empty_query_returns_400(
    desktop_client: TestClient, auth_headers: dict[str, str], registered: str
) -> None:
    resp = desktop_client.get(
        f"/projects/{registered}/search?q=", headers=auth_headers
    )
    assert resp.status_code == 422  # FastAPI validation for min_length


def test_search_unknown_project_returns_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.get(
        "/projects/deadbeefdeadbeef/search?q=anything",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_search_requires_auth(
    desktop_client: TestClient, registered: str
) -> None:
    resp = desktop_client.get(f"/projects/{registered}/search?q=x")
    assert resp.status_code == 401


def test_index_status_unknown_project_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.get(
        "/projects/deadbeefdeadbeef/search/index",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_post_index_starts_job(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vlogkit.server.routes import search as search_route

    called = []

    def fake_build(project):
        called.append(project)

    monkeypatch.setattr(search_route, "_do_index", fake_build)

    resp = desktop_client.post(
        f"/projects/{registered}/search/index", headers=auth_headers
    )
    assert resp.status_code == 202
    assert "job_id" in resp.json()


def test_search_returns_503_when_deps_missing(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vlogkit.server.routes import search as search_route

    def fake_search(project, query: str, k: int = 10):
        raise ImportError("No module named 'sentrysearch'")

    monkeypatch.setattr(search_route, "_do_search", fake_search)

    resp = desktop_client.get(
        f"/projects/{registered}/search?q=x", headers=auth_headers
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "search_extras_not_installed"
```

- [ ] **Step 3: Implement `src/vlogkit/server/routes/search.py`**

Template — adapt to real `vlogkit.search` signatures:

```python
"""/projects/{id}/search: query + index."""
from __future__ import annotations

import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from vlogkit.project import Project
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import (
    ErrorDetail,
    IndexStatus,
    SearchHit,
    SearchResponse,
)


def _do_search(project: Project, query: str, k: int = 10) -> list[dict]:
    """Real search — adapter over vlogkit.search. Monkey-patchable in tests."""
    from vlogkit.search.query import search as _search  # lazy import
    results = _search(project, query, k=k)
    # Normalize to a list of dicts matching SearchHit
    return [_hit_to_dict(r) for r in results]


def _do_index(project: Project) -> None:
    """Real index build — monkey-patchable in tests."""
    from vlogkit.search.indexer import build_index  # lazy import
    build_index(project)


def _do_stats(project: Project) -> dict:
    from vlogkit.search.query import index_stats  # lazy import
    return index_stats(project)


def _hit_to_dict(r) -> dict:
    # Adapt to whatever shape vlogkit.search.query.search returns.
    # If it's already a dict with the right keys, this is identity.
    return dict(r)


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["search"],
        dependencies=[Depends(require_token)],
    )

    @router.get(
        "/search",
        response_model=SearchResponse,
        responses={
            404: {"model": ErrorDetail},
            503: {"model": ErrorDetail},
        },
    )
    def search(
        project_id: str,
        q: str = Query(..., min_length=1),
        k: int = Query(10, ge=1, le=50),
        registry: ProjectRegistry = Depends(get_registry),
    ) -> SearchResponse:
        project = load_project(registry, project_id)
        try:
            hits = _do_search(project, q, k=k)
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail=ErrorDetail(
                    code="search_extras_not_installed",
                    message="Install optional deps: pip install -e '.[search]'",
                ).model_dump(),
            )
        return SearchResponse(
            query=q, hits=[SearchHit(**h) for h in hits]
        )

    @router.get(
        "/search/index",
        response_model=IndexStatus,
        responses={
            404: {"model": ErrorDetail},
            503: {"model": ErrorDetail},
        },
    )
    def get_index_status(
        project_id: str,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> IndexStatus:
        project = load_project(registry, project_id)
        try:
            stats = _do_stats(project)
        except ImportError:
            raise HTTPException(
                status_code=503,
                detail=ErrorDetail(
                    code="search_extras_not_installed",
                    message="Install optional deps: pip install -e '.[search]'",
                ).model_dump(),
            )
        indexed = stats.get("indexed", 0)
        total = stats.get("total", 0)
        return IndexStatus(
            indexed=indexed, total=total, ready=indexed >= total and total > 0
        )

    @router.post(
        "/search/index",
        status_code=status.HTTP_202_ACCEPTED,
        responses={404: {"model": ErrorDetail}},
    )
    def start_index(
        project_id: str,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> dict[str, str]:
        project = load_project(registry, project_id)
        job_id = uuid.uuid4().hex

        def run():
            try:
                _do_index(project)
            except Exception as exc:
                # Errors are swallowed; the next GET /search/index will
                # report whatever stats exist. A future plan can add WS
                # events for index progress + failures.
                print(f"[index] job {job_id} failed: {exc}", flush=True)

        threading.Thread(target=run, daemon=True).start()
        return {"job_id": job_id}

    return router
```

- [ ] **Step 4: Register in `create_desktop_app`**

Edit `src/vlogkit/server/app.py`:

```python
from vlogkit.server.routes import search as search_routes
# ...
app.include_router(search_routes.create_router())
```

- [ ] **Step 5: Regenerate OpenAPI snapshot + run tests**

```
VLOGKIT_UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/server/test_openapi_snapshot.py -v
.venv/bin/pytest -v
```

Expect **89 passed** (82 + 7 from test_search.py).

- [ ] **Step 6: Commit**

```bash
git add src/vlogkit/server/schemas.py src/vlogkit/server/routes/search.py src/vlogkit/server/app.py tests/server/test_search.py tests/server/snapshots/openapi.json
git commit -m "feat(server): semantic search routes with graceful dep fallback"
```

---

## Task 2: Frontend search API + types

**Files:**
- Regenerate: `desktop/web/src/lib/api-types.ts`
- Modify: `desktop/web/src/lib/api.ts`

- [ ] **Step 1: Regen types**

```bash
bash desktop/scripts/gen-api-types.sh
```

Verify `SearchHit`, `SearchResponse`, `IndexStatus` appear in `components/schemas`.

- [ ] **Step 2: Add to `lib/api.ts`**

Add aliases at the top:

```typescript
type SearchHit = components["schemas"]["SearchHit"];
type SearchResponse = components["schemas"]["SearchResponse"];
type IndexStatus = components["schemas"]["IndexStatus"];
```

Methods in the `api` object:

```typescript
searchClips: (projectId: string, query: string, k = 10) =>
  request<SearchResponse>(
    `/projects/${projectId}/search?q=${encodeURIComponent(query)}&k=${k}`,
  ),
buildSearchIndex: (projectId: string) =>
  request<{ job_id: string }>(`/projects/${projectId}/search/index`, {
    method: "POST",
  }),
getIndexStatus: (projectId: string) =>
  request<IndexStatus>(`/projects/${projectId}/search/index`),
```

Re-exports:

```typescript
export type { Project, ClipSummary, ErrorDetail, Storyboard, StoryboardSection, StoryboardSegment, SearchHit, SearchResponse, IndexStatus };
```

- [ ] **Step 3: Typecheck + build**

```bash
cd desktop/web && npx tsc --noEmit && npm run build
```

- [ ] **Step 4: Commit**

```bash
git add desktop/web/src/lib desktop/web/src/lib/api-types.ts
git commit -m "feat(desktop): search API types and client methods"
```

---

## Task 3: Search panel UI

**Files:**
- Create: `desktop/web/src/components/search/search-panel.tsx`
- Create: `desktop/web/src/components/search/search-bar.tsx`
- Create: `desktop/web/src/components/search/result-card.tsx`
- Create: `desktop/web/src/components/search/index-prompt.tsx`
- Modify: `desktop/web/src/app/project/page.tsx`

- [ ] **Step 1: `search-bar.tsx`**

```tsx
"use client";

import { useState } from "react";

export function SearchBar({
  onSubmit,
  initial = "",
}: {
  onSubmit: (q: string) => void;
  initial?: string;
}) {
  const [value, setValue] = useState(initial);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim()) onSubmit(value.trim());
      }}
      className="flex gap-2"
    >
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Describe what you're looking for…"
        className="flex-1 rounded-[4px] border border-[var(--color-border-whisper)] bg-white px-3 py-2 text-sm"
      />
      <button
        type="submit"
        disabled={!value.trim()}
        className="px-4 py-2 rounded-[4px] font-semibold text-sm text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60"
      >
        Search
      </button>
    </form>
  );
}
```

- [ ] **Step 2: `result-card.tsx`**

```tsx
import type { SearchHit } from "@/lib/api";

export function ResultCard({
  hit,
  onDragStart,
}: {
  hit: SearchHit;
  onDragStart?: (e: React.DragEvent) => void;
}) {
  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "copy";
        e.dataTransfer.setData(
          "application/vlogkit-hit",
          JSON.stringify(hit),
        );
        onDragStart?.(e);
      }}
      className="bg-white rounded-[8px] border border-[var(--color-border-whisper)] p-3 cursor-grab active:cursor-grabbing"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="font-semibold text-sm truncate">
          {hit.clip_filename}
        </div>
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-[var(--color-badge-bg)] text-[var(--color-badge-text)]">
          {Math.round(hit.score * 100)}%
        </span>
      </div>
      <div className="text-xs text-[var(--color-placeholder)] mt-1">
        {hit.chunk_start.toFixed(1)}s → {hit.chunk_end.toFixed(1)}s
      </div>
      {hit.snippet ? (
        <p className="text-xs text-[var(--color-muted)] mt-2 line-clamp-3">
          {hit.snippet}
        </p>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 3: `index-prompt.tsx`**

Shown when no index exists yet OR when the optional deps are missing.

```tsx
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/lib/api";

export function IndexPrompt({
  projectId,
  reason,
}: {
  projectId: string;
  reason: "missing_deps" | "empty_index";
}) {
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: () => api.buildSearchIndex(projectId),
    onSuccess: () => qc.invalidateQueries(),
  });

  if (reason === "missing_deps") {
    return (
      <div className="text-center py-16 px-8">
        <h2 className="text-xl font-bold mb-2">Search extras not installed</h2>
        <p className="text-[var(--color-muted)] max-w-md mx-auto text-sm">
          Install the optional dependencies to enable semantic search:
        </p>
        <code className="block mt-3 text-xs bg-[var(--color-background-alt)] rounded-[4px] px-3 py-2 inline-block">
          pip install -e &apos;.[search]&apos;
        </code>
      </div>
    );
  }

  return (
    <div className="text-center py-16 px-8">
      <h2 className="text-xl font-bold mb-2">No search index yet</h2>
      <p className="text-[var(--color-muted)] max-w-md mx-auto mb-5 text-sm">
        Build a search index of this project&apos;s analyzed clips so you can
        search by visual content (e.g. &quot;sunset over bridge&quot;).
      </p>
      <button
        onClick={() => mut.mutate()}
        disabled={mut.isPending}
        className="px-4 py-2 rounded-[4px] font-semibold text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60"
      >
        {mut.isPending ? "Starting index…" : "Build index"}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: `search-panel.tsx`**

```tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { SearchBar } from "./search-bar";
import { ResultCard } from "./result-card";
import { IndexPrompt } from "./index-prompt";

export function SearchPanel({ projectId }: { projectId: string }) {
  const [query, setQuery] = useState<string | null>(null);

  const indexStatus = useQuery({
    queryKey: [...queryKeys.project(projectId), "search-index"],
    queryFn: () => api.getIndexStatus(projectId),
    retry: false,
    refetchInterval: (q) => (q.state.data?.ready ? false : 3000),
  });

  const results = useQuery({
    queryKey: [...queryKeys.project(projectId), "search", query],
    queryFn: () => api.searchClips(projectId, query!),
    enabled: !!query && !!indexStatus.data?.ready,
  });

  // Deps missing → 503
  if (
    indexStatus.error instanceof ApiError &&
    indexStatus.error.code === "search_extras_not_installed"
  ) {
    return <IndexPrompt projectId={projectId} reason="missing_deps" />;
  }

  // No index yet
  if (!indexStatus.data || indexStatus.data.total === 0) {
    return <IndexPrompt projectId={projectId} reason="empty_index" />;
  }

  return (
    <div className="space-y-4">
      <SearchBar onSubmit={setQuery} />
      {!indexStatus.data.ready ? (
        <p className="text-sm text-[var(--color-muted)]">
          Indexing… {indexStatus.data.indexed}/{indexStatus.data.total} clips
          ({Math.round(
            (indexStatus.data.indexed / indexStatus.data.total) * 100,
          )}
          %)
        </p>
      ) : null}
      {results.isLoading ? (
        <p className="text-sm text-[var(--color-muted)]">Searching…</p>
      ) : null}
      {results.data ? (
        <div>
          <p className="text-sm text-[var(--color-muted)] mb-2">
            {results.data.hits.length} result
            {results.data.hits.length === 1 ? "" : "s"} for &ldquo;
            {results.data.query}&rdquo;
          </p>
          <div className="grid grid-cols-2 gap-3">
            {results.data.hits.map((h, i) => (
              <ResultCard key={i} hit={h} />
            ))}
          </div>
          {results.data.hits.length === 0 ? (
            <p className="text-sm text-[var(--color-placeholder)] py-8 text-center">
              No matches. Try different keywords.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 5: Wire into `page.tsx`**

Replace `{tab === "search" && <Placeholder name="Semantic search — Plan 5" />}` with:

```tsx
{tab === "search" && <SearchPanel projectId={id} />}
```

Add import: `import { SearchPanel } from "@/components/search/search-panel";`

- [ ] **Step 6: Typecheck + build**

```bash
cd desktop/web && npx tsc --noEmit && npm run build
```

- [ ] **Step 7: Commit**

```bash
git add desktop/web/src/components/search desktop/web/src/app/project/page.tsx
git commit -m "feat(desktop): semantic search panel with query + index prompt"
```

---

## Task 4: Drag search result to board

Hook up drops. Drop target: the end of any section on the board. Dropped result inserts a new `StoryboardSegment` with `clip_path`, `in_point=hit.chunk_start`, `out_point=hit.chunk_end`, `label="(from search)"`.

User flow: user is on the board tab → opens search in a **separate tab** (no — we only have tabs). OK, revised: user stays on the board tab, and the search panel is rendered as a collapsible sidebar on the board tab itself, OR we punt on drag-across-tabs and just add a "Insert at end of section X" dropdown on the result card.

**Decision: dropdown approach.** It's simpler and doesn't require a new UX pattern. Drag-across-tabs isn't a native HTML behavior anyway. Each result card gets a small button "+ Insert into section…" that opens a list of sections and inserts on click.

**Files:**
- Modify: `desktop/web/src/components/search/result-card.tsx` — add insert button
- Create: `desktop/web/src/components/search/insert-into-section.tsx`

- [ ] **Step 1: `insert-into-section.tsx`**

```tsx
"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type Storyboard, type SearchHit } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

export function InsertIntoSection({
  projectId,
  hit,
}: {
  projectId: string;
  hit: SearchHit;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const { data: storyboard, error } = useQuery({
    queryKey: [...queryKeys.project(projectId), "storyboard"],
    queryFn: () => api.getStoryboard(projectId),
    retry: false,
  });

  if (error instanceof ApiError && error.code === "storyboard_not_found") {
    return (
      <span className="text-xs text-[var(--color-placeholder)]">
        Generate a storyboard first
      </span>
    );
  }
  if (!storyboard) return null;
  const sections = storyboard.sections ?? [];

  async function insertInto(sectionIndex: number) {
    const next: Storyboard = JSON.parse(JSON.stringify(storyboard));
    const sec = (next.sections ?? [])[sectionIndex];
    if (!sec) return;
    const segments = sec.segments ?? [];
    segments.push({
      clip_path: hit.clip_filename,
      in_point: hit.chunk_start,
      out_point: hit.chunk_end,
      label: "(from search)",
      transition: "",
      include: true,
    });
    sec.segments = segments;
    await api.putStoryboard(projectId, next);
    qc.invalidateQueries({
      queryKey: [...queryKeys.project(projectId), "storyboard"],
    });
    setOpen(false);
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-xs font-semibold text-[var(--color-accent)] hover:text-[var(--color-accent-strong)]"
      >
        + Insert into section
      </button>
      {open ? (
        <div
          className="absolute right-0 mt-1 bg-white border border-[var(--color-border-whisper)] rounded-[8px] shadow-lg z-10 min-w-[180px]"
          style={{ boxShadow: "var(--shadow-deep)" }}
        >
          {sections.map((s, i) => (
            <button
              key={i}
              onClick={() => insertInto(i)}
              className="block w-full text-left px-3 py-2 text-sm hover:bg-[var(--color-background-alt)]"
            >
              {s.title}
            </button>
          ))}
          {sections.length === 0 ? (
            <p className="p-3 text-xs text-[var(--color-placeholder)]">
              No sections yet
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: Wire button into `result-card.tsx`**

Replace the existing `result-card.tsx` body — keep the card visuals, add the insert button at the bottom:

```tsx
import type { SearchHit } from "@/lib/api";
import { InsertIntoSection } from "./insert-into-section";

export function ResultCard({
  projectId,
  hit,
}: {
  projectId: string;
  hit: SearchHit;
}) {
  return (
    <div
      className="bg-white rounded-[8px] border border-[var(--color-border-whisper)] p-3"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="font-semibold text-sm truncate">
          {hit.clip_filename}
        </div>
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-[var(--color-badge-bg)] text-[var(--color-badge-text)]">
          {Math.round(hit.score * 100)}%
        </span>
      </div>
      <div className="text-xs text-[var(--color-placeholder)] mt-1">
        {hit.chunk_start.toFixed(1)}s → {hit.chunk_end.toFixed(1)}s
      </div>
      {hit.snippet ? (
        <p className="text-xs text-[var(--color-muted)] mt-2 line-clamp-3">
          {hit.snippet}
        </p>
      ) : null}
      <div className="mt-3 flex justify-end">
        <InsertIntoSection projectId={projectId} hit={hit} />
      </div>
    </div>
  );
}
```

Drop the `draggable` / `onDragStart` props from the earlier version — the dropdown is the chosen UX.

- [ ] **Step 3: Update `search-panel.tsx` to pass `projectId` to `ResultCard`**

One-line change:

```tsx
{results.data.hits.map((h, i) => (
  <ResultCard key={i} projectId={projectId} hit={h} />
))}
```

- [ ] **Step 4: Typecheck + build**

```bash
cd desktop/web && npx tsc --noEmit && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add desktop/web/src/components/search
git commit -m "feat(desktop): insert search result into storyboard section"
```

---

## Task 5: Verification + Plan 5 review

- [ ] **Step 1: Full backend suite**

`.venv/bin/pytest -v` → expect **89 passed**.

- [ ] **Step 2: Desktop build**

```bash
cd desktop && npm run build
```

- [ ] **Step 3: Manual smoke**

Launch and walk through:
1. Open folder, analyze, generate storyboard
2. Switch to **search** tab
3. If `[search]` extras aren't installed → "Search extras not installed" page with pip command
4. If installed but no index → "Build index" prompt → click → indexing status appears
5. Once indexed, type a query → results grid with scores + snippets
6. On a result card, click "+ Insert into section" → dropdown of section titles → click one → board gains a new segment labeled "(from search)" at the end of that section
7. Switch back to board tab → confirm the new segment is there

- [ ] **Step 4: Write `docs/superpowers/plans/2026-04-17-plan-5-review.md`**

Usual template. Expected rough edges:
- No WS progress events for indexing (uses polling every 3s)
- Dropdown UX for inserting isn't as snappy as native drag-drop, but works
- New segments inserted from search have `clip_path` set to `hit.clip_filename` only (not a full path) — the existing storyboard may use full paths; mixing could confuse the inspector preview (basename lookup still works)
- Score is displayed as a percentage but sentrysearch scores are typically cosine distances (0–1 but not strictly comparable across queries)
- No pagination of results — limited to `k=10`
- No clip thumbnail in result cards — just filename + times + snippet

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-04-17-plan-5-review.md
git commit -m "docs: plan 5 review + carry-over items"
```

---

## Self-Review Notes

- Task 0 lands the Plan 4 carry-over before Task 1 adds a 6th route file.
- Task 1's `_do_search`, `_do_index`, `_do_stats` module-level functions are the monkey-patch seams for tests. Real implementations lazy-import `vlogkit.search` so the routes register even when `[search]` extras aren't installed.
- Task 4 ditched drag-across-tabs in favor of a dropdown — simpler, same functional outcome, no new UX pattern.
- Each step contains real code. No placeholders.
