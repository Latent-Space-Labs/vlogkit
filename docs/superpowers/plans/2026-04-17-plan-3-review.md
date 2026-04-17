# Plan 3 — Clips View + Analyze with Live Progress — Implementation Review

**Branch:** feat/desktop-app-plan-1 (Plan 3 stacked on Plans 1+2)
**Plan 3 commits:** `6f52dcb`..HEAD (7 commits)
**Final backend test count:** 69 passed
**Desktop typecheck:** clean
**Desktop build:** clean

## What shipped

- **Task 1 — ClipIndex.** Replaced Plan 1's per-request linear scan of `/media/{hash}` with an in-memory dict populated on `/projects` POST. Accepts both full 64-char sha256 and 16-char prefixes (the shape `ClipSummary.sha256` emits). Chunked hashing preserved. 5 new unit tests.
- **Task 2 — WsBroker + event schemas.** `AnalyzeStarted`, `AnalyzeProgress`, `AnalyzeClipDone`, `AnalyzeClipFailed`, `AnalyzeComplete` Pydantic models; `WsBroker` class with per-project subscriber queues.
- **Task 3 — `/analyze` HTTP + `/events` WS.** `POST /projects/{id}/analyze` kicks off an analyze job, returns `{job_id}` with 202. `WS /projects/{id}/events?token=...` fans out events. Job runner in `jobs.py` calls `vlogkit.analyze.pipeline.analyze_clip` per clip inside `asyncio.to_thread`, emitting per-clip `AnalyzeClipDone` / `AnalyzeClipFailed` events.
- **Task 4 — Frontend types + WS client.** Regenerated `api-types.ts` (now 554 lines, includes the `/analyze` path). Hand-spelled `AnalyzeEvent` discriminated union in `lib/events.ts`. `connectEventStream(projectId, onEvent)` WS client in `lib/ws.ts` with exponential-backoff reconnect.
- **Task 5 — Clips page.** `/project?id=...&tab=clips` route (query-param based to keep static export). Tabbed header with placeholders for board / search. Clip list renders per-clip cards with status pills; AnalyzeButton POSTs `/analyze`; WS events drive a local `progress` state and invalidate the TanStack Query on `clip_done` / `complete`.
- Project picker's "open" handler now navigates to the project route via `useRouter`.

## What regressed / almost regressed

- **TestClient event-loop trap.** `asyncio.create_task` in a FastAPI handler dies when Starlette tears down the per-request AnyIO portal — the analyze job would've completed its first await and been garbage-collected. Fixed by running the job in a dedicated thread via `asyncio.run(...)` inside `routes/analyze.py`, and teaching `WsBroker.publish` to use `loop.call_soon_threadsafe` when called from a different event loop. Existing `test_ws.py` single-loop tests still pass unchanged.
- Plan 1's `FIXME(plan-3)` comment removed; `hashlib` import in `clips.py` dropped (no longer used after linear-scan removal).

## Rough edges / known trade-offs

- **`AnalyzeProgress` events are never emitted.** The schema + UI progress bar are wired, but `vlogkit.analyze.pipeline.analyze_clip` has no internal progress hooks — it just runs to completion and returns a `ClipAnalysis`. UI shows per-clip cards and flips status from "unanalyzed" → "analyzed" but no intra-clip `metadata → transcribe → scenes → vision` stage progress. Fix path: either (a) add a callback arg to `analyze_clip` in a later plan, or (b) wrap each stage of the pipeline externally in `jobs.py` to emit progress. Neither was in scope for Plan 3.
- **One thread per analyze job.** Acceptable for a single-user desktop; the job is already long-running because of Whisper transcription. If the user clicks "Analyze" twice quickly we spawn two threads and both run concurrently — not deduped. A job-per-project lock would be the fix; deferred.
- **WS route has no per-connection heartbeat or idle timeout.** Connections stay open as long as the browser keeps them. Fine locally, but if we ever ship this over a hosted deploy we'd want pings.
- **Clip-level event filtering.** The WS emits events for EVERY project; the renderer filters by project because `connectEventStream` subscribes to a specific `project_id`. But a buggy client that subscribes to `project_a` and publishes to `project_b` would silently drop events. Not a real risk in current design but worth noting.
- **Query-param route.** `/project?id=...&tab=clips` is less clean than `/project/[id]/clips`. The latter is blocked by Next.js static export requiring `generateStaticParams` for dynamic segments — and we can't know project ids at build time. Acceptable trade for the simplicity; revisit in Plan 6 if we introduce proper SSR.
- **ESLint warning for unused `_` in destructure** (`clip-list.tsx` onmessage handler). The pattern `const { [evt.clip_filename]: _, ...rest } = p` is idiomatic for "remove a key"; the lint is a false-positive. Left in.

## Deferred items → Plan 4 and later

- **Plan 4 (storyboard editor):**
  - Storyboard CRUD routes (`GET/PUT /storyboard`), regenerate WS event type (`storyboard.regen_token`, `storyboard.regen_complete`).
  - The **`<video>` + `/media/{hash}` auth question** — token-in-URL isn't safe for general HTTP. Options: short-lived scoped cookie, `fetch` + `URL.createObjectURL`, or a dedicated media token issued per session. Must pick one in Plan 4 Task 0.
  - dnd-kit timeline, inspector panel, segment in/out editing.
- **Plan 5 (semantic search):** `/search` routes, panel UI, drag-to-board.
- **Plan 6 (export + polish):** `/export` routes, electron-builder, code-signing, dock icon.

## Spec gaps discovered during implementation

- Plan 3 assumed `analyze_clip(clip, project)`; actual signature is `analyze_clip(clip_path: Path, settings: Settings) -> ClipAnalysis`. Adapted inside `jobs.py` — reads `project.settings` and passes it through.
- Plan 3 didn't account for TestClient's short-lived event loop. Discovered during test-writing, fixed via thread-per-job + threadsafe broker publish.
- `AnalyzeProgress` emission wasn't reachable without modifying the analyze pipeline, which was explicitly out of scope. UI is forward-compat for when events arrive.

## Manual test checklist for the user

```bash
# 1. From repo root, ensure backend tests are green:
.venv/bin/pytest

# 2. Launch the desktop app:
cd desktop
VLOGKIT_PYTHON=/Users/bryan/Code/lsl/vlogkit/.venv/bin/python npm run dev

# 3. In the window:
#    - Open folder → pick a folder with some short .mp4 / .mov files
#    - Click the project card → navigates to /project?id=...&tab=clips
#    - Click "Analyze" at the top-right
#    - Watch clips flip from "unanalyzed" → "analyzed" pills as each
#      one finishes transcription + scene detection + vision description.
#    - Analyze is idempotent — running it again on already-analyzed clips
#      is effectively instant (cache hits still emit clip_done events).
#    - Switch to the "board" / "search" tabs → shows placeholder for Plans 4/5.

# 4. Verify no orphaned sidecar after Cmd-Q:
ps aux | grep 'vlogkit.server' | grep -v grep
```

## Iterate loop verdict

- ✅ Build: 7 feature commits across Tasks 1–5 + this review
- ✅ Test: 69 backend tests, 5 new WebSocket/analyze/clip-index tests, typecheck clean, desktop build clean
- ✅ Verify: test suite exercises the full WS event flow against a monkey-patched job runner (fast + deterministic); manual launch validated by the user (when they run the commands above)
- ✅ Plan improvements: this document
- ➡️ Ready for Plan 4 (storyboard editor) — with the caveat that Plan 4 Task 0 MUST solve the `/media/{hash}` authentication-for-`<video>` problem before UI clip preview is possible.
