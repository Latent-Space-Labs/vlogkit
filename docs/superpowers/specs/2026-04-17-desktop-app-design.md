# vlogkit Desktop App — Design Spec

**Date:** 2026-04-17
**Status:** Draft for review
**Scope:** A storyboard-focused desktop app on top of the existing vlogkit Python pipeline.

---

## 1. Goal

Turn the existing `vlogkit` CLI pipeline (`init → analyze → storyboard → review → export`) into a desktop application whose hero experience is a rich, visual storyboard editor. The CLI keeps working standalone; the desktop app is a second consumer of the same underlying library.

## 2. Non-goals (v1)

- Full NLE (no multi-track compositing, no advanced trimming, no effects).
- Cross-platform packaging polish — macOS is the primary target; Windows works but is not the v1 focus.
- In-app settings UI — configuration stays in env vars via the existing `pydantic-settings` loader.
- Cloud sync, user accounts, telemetry.

## 3. Tech stack

- **Shell:** Electron (Chromium + Node.js main process)
- **UI:** Next.js 15 (App Router) in `output: 'export'` static-export mode, React 19, TypeScript, Tailwind CSS, shadcn/ui
- **Design language:** Notion-inspired, as defined in [DESIGN.md](../../../DESIGN.md) at the repo root. All new UI must use tokens from that file — warm neutrals, whisper borders, NotionInter typography, 4px/12px/16px radius scale, 4–5 layer shadow stacks.
- **State:** TanStack Query for server state, Zustand for UI state
- **Drag-and-drop:** dnd-kit
- **Video preview:** `<video>` element against Range-enabled `/media/{hash}` endpoint
- **Python backend:** Existing vlogkit codebase + extended FastAPI server (`server.py`) launched as an Electron sidecar
- **Type safety across the boundary:** `openapi-typescript` generates TS client types from the running sidecar's `/openapi.json`
- **Testing:** pytest (backend), Vitest + React Testing Library (unit), Playwright (E2E), MSW (mocked sidecar)

## 4. Architecture

Three processes, one installer:

```
┌────────────────────────────────────────┐
│ Electron Main (Node.js)                │
│  - Window/menu/native dialog           │
│  - Spawns & supervises Python sidecar  │
│  - Picks random port + auth token      │
│  - File drag-drop, recent projects     │
└───────┬──────────────────────┬─────────┘
        │ preload IPC          │ spawn
        ▼                      ▼
┌──────────────────┐   ┌───────────────────┐
│ Renderer         │   │ Python sidecar    │
│  Next.js export  │◄─►│  FastAPI +        │
│  React 19 UI     │HTTP  uvicorn on       │
│  TanStack Query  │  │  127.0.0.1:<rand>  │
│  Zustand         │WS │                   │
│  dnd-kit         │   │  Extends          │
│  shadcn/ui       │   │  existing         │
│                  │   │  vlogkit library  │
└──────────────────┘   └───────────────────┘
```

### 4.1 Sidecar lifecycle (authoritative — Electron Main owns this)

1. Electron Main launches → generates random 32-byte auth token → picks a free ephemeral port.
2. Main spawns Python sidecar: `python -m vlogkit.server --port <P> --token <T> --bind 127.0.0.1`.
3. Main polls `GET http://127.0.0.1:<P>/healthz` with a 10 s timeout; on 200 it creates the BrowserWindow.
4. Preload script exposes `window.vlogkit.apiPort` (number) and `window.vlogkit.token` (string) via `contextBridge.exposeInMainWorld`.
5. Renderer's `lib/api.ts` reads both at module init and attaches the `Authorization: Bearer` header to every request and WS connect.
6. On app quit: Main sends SIGTERM to sidecar, waits 3 s, then SIGKILL. All spawned child processes are tracked so a force-quit does not leak a background uvicorn.
7. On unexpected sidecar exit: see "Crash resilience" below — renderer never spawns or manages the sidecar itself.

**Crash resilience:** If the sidecar dies, Main restarts it up to 3× in 60 s. Renderer sees WS disconnect, shows a "Reconnecting…" toast, auto-refetches on reconnect. Analyze jobs are idempotent (clip hash cache), so re-running just picks up where it left off.

## 5. Frontend structure

### Routes (Next.js App Router, static-exported)

| Path                         | Purpose                                            |
|------------------------------|----------------------------------------------------|
| `/`                          | Project picker: recent projects + "Open folder…"  |
| `/project/[id]`              | Editor shell with tabs                            |
| `/project/[id]/clips`        | Clip library + per-clip analyze status            |
| `/project/[id]/board`        | **Storyboard timeline (hero view)**               |
| `/project/[id]/search`       | Semantic search panel                             |

Project `id` is a stable hash of the absolute folder path, computed server-side on registration.

### Component layers

- `app/` — thin route components, compose layouts + data
- `components/board/` — timeline, section row, segment block, inspector panel
- `components/clip/` — clip card, progress pill, preview player
- `components/search/` — query bar, result grid, hit card
- `components/ui/` — shadcn primitives
- `lib/api.ts` — typed fetch client (generated from OpenAPI)
- `lib/ws.ts` — WebSocket client with reconnect + typed events
- `lib/ipc.ts` — thin preload bridge wrapper (open folder, reveal in Finder, port/token)

### State

- **TanStack Query** — all server state, keyed by project id; mutations invalidate queries precisely.
- **Zustand** — UI-only: selected segment, inspector open/closed, timeline zoom, drag previews.
- No Redux.

### Interactions

- **dnd-kit** for reorderable sections/segments (keyboard accessible).
- **Inspector** (right drawer) edits segment title / in / out; debounced 500 ms save.
- **Search → drag to board** inserts a new segment at the drop index.

## 6. Python backend (FastAPI)

### Module layout

```
src/vlogkit/server/
  app.py            # FastAPI factory, CORS, token auth middleware
  routes/
    projects.py
    clips.py
    analyze.py
    storyboard.py
    search.py
    export.py
  ws.py             # WebSocket broker, channel-per-project
```

The existing `server.py` (upload server) merges into this new module.

### REST endpoints

```
GET    /healthz                         → liveness probe (unauth)
GET    /projects                        → list recent
POST   /projects                        → register from folder path
GET    /projects/{id}                   → project summary
DELETE /projects/{id}                   → forget (files untouched)

GET    /projects/{id}/clips             → clip list + status
GET    /projects/{id}/clips/{hash}      → single clip analysis
GET    /media/{hash}                    → Range-aware video stream
GET    /media/{hash}/thumb              → keyframe thumbnail

POST   /projects/{id}/analyze           → start job, returns job_id
GET    /projects/{id}/analyze/status    → current job status

GET    /projects/{id}/storyboard        → full storyboard JSON
PUT    /projects/{id}/storyboard        → replace
POST   /projects/{id}/storyboard/regenerate  → LLM regen job
POST   /projects/{id}/storyboard/sections/{idx}/segments/reorder
                                        → patch-style common ops

POST   /projects/{id}/search/index      → build/refresh index
GET    /projects/{id}/search?q=…        → semantic query

POST   /projects/{id}/export            → returns path to exported file
```

### WebSocket

Single connection per project: `WS /projects/{id}/events`.

| Event                             | Payload                                      |
|-----------------------------------|----------------------------------------------|
| `analyze.started`                 | `{ job_id, clip_count }`                     |
| `analyze.progress`                | `{ clip_hash, stage, pct }`                  |
| `analyze.clip_done`               | `{ clip_hash, analysis }`                    |
| `analyze.clip_failed`             | `{ clip_hash, error }`                       |
| `analyze.complete`                | `{ job_id, duration_s }`                     |
| `storyboard.regen_started`        | `{ job_id }`                                 |
| `storyboard.regen_token`          | `{ token }` *(optional streaming)*          |
| `storyboard.regen_complete`       | `{ storyboard }`                             |
| `index.progress`                  | `{ indexed, total }`                         |
| `error`                           | `{ code, message, context }`                 |

### Auth

Every HTTP and WS request carries `?token=…` or `Authorization: Bearer …`. Middleware rejects missing/wrong with 401. Token is generated by Electron Main per launch, passed to sidecar via flag, to renderer via preload.

### Data contracts

Pydantic models (`ClipAnalysis`, `Storyboard`, `StoryboardSection`, `StoryboardSegment`) serve double duty as FastAPI response models. OpenAPI schema is generated automatically; `openapi-typescript` runs in CI against a booted sidecar and the generated `lib/api.ts` is committed — drift breaks type-check.

### Jobs

In-process asyncio tasks, not Celery. Each job publishes to its project's WS channel. Sidecar crash → any in-flight job lost; safe because analyze is hash-cached and storyboard regen is idempotent.

## 7. User journeys

**Journey 1 — Open a folder, watch analysis:**
drag folder → Main `ipc.openProject` → `POST /projects` → navigate to `/project/:id/clips` → `GET clips` (shows unanalyzed/cached status) → user clicks Analyze → `POST /analyze` → WS streams per-clip progress → each clip card updates independently via `queryClient.setQueryData` (no list-wide re-render).

**Journey 2 — Generate and edit the storyboard:**
user clicks Generate → `POST /storyboard/regenerate` → WS streams optional `regen_token` events for a live text feel → on `regen_complete`, board view loads → user drags segment to reorder → optimistic Zustand update + `PUT /storyboard` → on error, TanStack Query rolls back → inspector edits debounce-save after 500 ms.

**Journey 3 — Semantic search to board:**
user types query → `GET /search?q=…` → thumbnails render with timestamp bands → user drags a hit into a section → insert at drop index via `PUT /storyboard` → board re-renders.

## 8. Error handling

- **Sidecar startup failure:** Main captures stderr, shows `dialog.showErrorBox` with last 20 lines, exits clean.
- **Sidecar crash mid-session:** Main auto-restarts up to 3×/60 s; renderer shows "Reconnecting…" toast; queries auto-refetch on reconnect.
- **Crash loop:** Main writes full log to `~/Library/Logs/vlogkit/sidecar-<ts>.log`, shows "Copy logs / Quit" dialog.
- **API errors:** uniform envelope `{ error: { code, message, context } }`; stable machine-readable `code` strings; UI maps known codes to friendly copy.
- **Per-clip analyze failure:** emits `analyze.clip_failed`, job continues; clip gets a red dot + retry affordance.
- **LLM regen failure:** full rollback, keep old storyboard, toast the reason.
- **React error boundary** at route level — board crash does not take down clip view.
- **Breadcrumb logging** to local file; no network telemetry in v1.
- **Segment validation:** server-side enforcement of in/out bounds and non-overlap; 422 with `code: "invalid_segment_bounds"`; client mirrors rules for immediate feedback.

## 9. Visual design

All UI derives from the Notion-inspired [DESIGN.md](../../../DESIGN.md) at the repo root. Non-negotiables:

- **Colors:** warm neutrals only (`#f6f5f4`, `#31302e`, `#615d59`, `#a39e98`); near-black text `rgba(0,0,0,0.95)` rather than pure black; Notion Blue (`#0075de`) as the sole saturated accent.
- **Typography:** NotionInter family with the 14-step scale; aggressive negative letter-spacing at display sizes (-2.125px at 64px); four weights (400/500/600/700).
- **Borders:** `1px solid rgba(0,0,0,0.1)` whisper borders throughout — no heavier dividers.
- **Shadows:** 4–5 layer stacks; individual layers ≤ 0.05 opacity.
- **Radius:** 4px for buttons/inputs, 12px standard cards, 16px hero/featured, 9999px for pill badges.
- **Spacing:** 8px base unit with the non-rigid organic scale defined in DESIGN.md.
- **Section rhythm:** alternating white and warm-white (`#f6f5f4`) section backgrounds.

Dark mode is a **fast-follow after v1** (palette inversion is not yet defined in DESIGN.md; will be designed separately).

## 10. Testing

**Backend (pytest):**
- Route unit tests with FastAPI `TestClient`.
- Job runner tests asserting WS event order and post-job cache state.
- One end-to-end integration with a tiny fixture video: analyze → storyboard → export. Keeps CLI↔desktop contract honest.

**Frontend:**
- Vitest + React Testing Library for component logic.
- Playwright for golden-path E2E against the built static export with MSW-mocked sidecar.
- MSW fixtures live next to the components they mock.

**Shell:**
- One Playwright-Electron smoke test: app launches, sidecar spawns, renderer reaches `/projects`.

**Type drift guard:**
- CI boots the real sidecar, runs `openapi-typescript` against `/openapi.json`, diffs against committed `lib/api.ts`. Non-zero diff fails the build.

**Deliberately out of scope for v1:**
- Visual regression testing
- Cross-platform packaging tests
- Load/performance tests

## 11. Implementation approach — iterative loop

Per explicit user requirement, implementation follows a strict **build → test → verify → plan improvements → iterate until done** cadence. Each chunk in the implementation plan must:

1. **Build** — ship the smallest working slice that advances the spec.
2. **Test** — unit + integration coverage for the slice, written in the same chunk.
3. **Verify** — run the tests and exercise the feature end-to-end (build the installer and click through the real UI path; don't rely on compile/typecheck alone).
4. **Plan improvements** — a short review at the end of each chunk: what regressed, what's awkward, what needs a follow-up. Capture as explicit next-chunk tasks.
5. **Iterate** — do not mark a chunk complete until the feature works end-to-end on real data.

The `writing-plans` step will turn each section of this spec into a chunk that follows this loop.

## 12. Repository layout (after implementation)

```
vlogkit/
  DESIGN.md                    # (new) Notion-inspired design language
  src/vlogkit/
    cli.py                     # unchanged — still the CLI entrypoint
    server/                    # (new) FastAPI routes, replaces server.py
    …existing modules unchanged…
  desktop/                     # (new) Electron + Next.js app
    electron/                  # Main process + preload
    web/                       # Next.js app (static-exported)
    package.json
  tests/
    …existing pytest tests plus new backend/server/ tests…
  docs/superpowers/specs/
    2026-04-17-desktop-app-design.md
```

## 13. Open questions / fast-follows (intentionally deferred)

- **Export dialog UX** — included as a minimal dialog in v1 (format picker + destination folder). Richer export UX (per-section exports, proxy ladders, etc.) is a fast-follow.
- **Dark mode** — needs palette extension in DESIGN.md before implementation.
- **In-app settings** — env-var only in v1; settings UI deferred.
- **Windows/Linux packaging polish** — works, but macOS is primary target.
- **Auto-update + code signing** — deferred; ad-hoc builds for v1.

---

**Next step:** invoke the `writing-plans` skill to decompose this spec into a reviewable, chunked implementation plan that follows the build → test → verify → iterate loop.
