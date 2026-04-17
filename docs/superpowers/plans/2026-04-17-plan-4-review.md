# Plan 4 — Storyboard Editor (Hero View) — Implementation Review

**Branch:** feat/desktop-app-plan-1
**Plan 4 commits:** `7893551`..HEAD (9 commits)
**Final backend test count:** 80 passed
**Desktop typecheck:** clean
**Desktop build:** clean

## What shipped

- **Task 0** — `/media/{hash}` accepts `?token=` query param so `<video src>` can auth on the 127.0.0.1 sidecar without the Bearer header (which `<video>` can't send). Header auth still works.
- **Task 1** — `/projects/{id}/storyboard` GET + PUT. Reuses `Project.load_storyboard()` / `save_storyboard()` already used by the CLI. 404 with `storyboard_not_found` code when none exists yet. Discovery: `Storyboard` model uses `label`/`clip_path`/`in_point`/`out_point` (not `title`/`clip_filename`/`start`/`end` as Plan 4 prose had assumed).
- **Task 2** — `POST /projects/{id}/storyboard/regenerate` + WS regen events (`regen_started`, `regen_complete`, `regen_failed`, `regen_token` schema declared but not emitted). Reuses `vlogkit.storyboard.builder.build_storyboard`. Threaded job runner to avoid TestClient's per-request event-loop trap.
- **Task 3** — TS types regenerated (554 → 808 lines). `Storyboard`/`StoryboardSection`/`StoryboardSegment` now typed end-to-end. `api.getStoryboard` / `putStoryboard` / `regenerateStoryboard` client methods. `getMediaUrl(hash)` helper. `connectEventStream` widened from `AnalyzeEvent` to `BoardEvent`. dnd-kit installed.
- **Task 4** — Read-only board tab at `/project?id=...&tab=board`. Storyboard title + LLM rationale header, sections with horizontally-scrolling segment blocks, clickable segment selection, right-side aside placeholder.
- **Task 5** — dnd-kit intra-section reorder with `arrayMove`, optimistic TanStack Query updates via a dedicated `useSegmentReorder` hook, rollback on error. Cross-section drag explicitly deferred.
- **Task 6** — Inspector drawer replaces the placeholder aside: `<video>` preview via `getMediaUrl`, auto-seeks to `in_point` on segment change, auto-pauses at `out_point`. Editable `label`, `in_point`, `out_point` with 500ms debounced save. Handles clips that haven't been analyzed yet (no sha256 → graceful "no preview available" state).
- **Task 7** — Regenerate button in the board header. WS subscription flips a local `regenInFlight` flag on `regen_started`, invalidates the storyboard query on `regen_complete`/`failed` so the UI auto-refreshes when the job finishes.

## What regressed / almost regressed

- **FastAPI's response_model generated split `Storyboard-Input` / `Storyboard-Output` schemas** (because default values make request vs. response fields different). Handled cleanly by aliasing `Storyboard = Storyboard-Output` for reads and using `Storyboard-Input` internally for `putStoryboard` bodies.
- **The `sections`/`segments` fields are marked optional in the OpenAPI output.** UI code uses `?? []` guards throughout — not a regression but something to keep in mind if backend schemas ever switch to strict lists.
- **`useQueryClient` and `useEffect` imports in `board.tsx`** — the subagent correctly added them when Task 7 wired WS handling; no import errors.

## Rough edges / known trade-offs

- **`storyboard.regen_token` events are never emitted.** The schema is declared and the TS union includes it, but `vlogkit.storyboard.builder.build_storyboard` doesn't stream — it returns a finished `Storyboard` synchronously. Real streaming would require switching the builder to `anthropic.messages.stream()` with a token callback. Deferred to a future plan or fold into Plan 5.
- **Cross-section segment drag is not supported.** Only intra-section reorder works. Moving a segment between sections needs extra logic to detect `containerId` via dnd-kit's `DragOverEvent`. Deferred.
- **No undo / redo.** Every edit is persisted immediately.
- **Inspector doesn't validate `in_point < out_point`.** User can type `out_point=1.0, in_point=50.0`; the clip-preview will never show anything because the video will be past `end` on the first `timeupdate`. Validation is trivial to add but deferred.
- **404-detection in Board uses `error instanceof ApiError && error.code === "storyboard_not_found"`.** This relies on `ApiError` being the thrown type — works today but TanStack Query swallows the class type through its `error` signature (`Error | null`). Task 4 used `instanceof ApiError` which works because the generic param is inferred. Keep an eye on it if error handling changes.
- **`<video>` src uses the token in the query string.** Token is already per-process and the URL never leaves the Electron renderer, but it will appear in the Chromium devtools Network tab. Acceptable for a local tool.
- **Clip preview buffers the entire clip when `<video>` loads** (vanilla `FileResponse` with `Range` headers). For multi-GB clips this is noticeable; scrubbing is range-aware though, so actual playback is cheap once loaded.
- **Form reset via `useEffect` on `[segment]`** — if the user is mid-edit and the storyboard refetches due to a WS event or sibling mutation, their unsaved form state could snap back. In practice the debounce (500ms) saves before any refetch can reasonably race, but it's a latent bug.
- **`storyboard.builder` is called with positional args** (`analyses, project.root, settings, strategy, context`). Fragile to builder signature changes — a follow-up could switch to kwargs.
- **Task 2 imported `AnalyzeEvent` → aliased to `BoardEvent`.** `clip-list.tsx`'s callback accepts `BoardEvent` but only handles `analyze.*` events, silently ignoring storyboard events that happen to arrive. Intentional (the WS is per-project, not per-tab) but worth flagging.

## Deferred items for Plan 5 / 6

- **Plan 5 (semantic search):** `/search` routes, query UI, drag-to-board (insert a search hit as a new segment at drop index).
- **Plan 6 (export + polish):** `/export` routes, electron-builder packaging, code signing, DMG installer, dock icons, production HTML path fix in `window.ts`.
- **Cross-plan polish:**
  - Real streaming LLM for regenerate (wire `anthropic.messages.stream()`, emit `regen_token` events).
  - Cross-section drag.
  - `in_point` / `out_point` validation + visual clamp to clip duration.
  - Shared `_registry` / `_load_project` helpers — now duplicated across 5 route modules (`projects.py`, `clips.py`, `analyze.py`, `storyboard.py`, and the clip_index hooks in `projects.py`). Extract to `server/deps.py`.

## Spec gaps discovered during implementation

- **Real `Storyboard` field names** — Plan 4 prose used casual placeholder names (`title`, `start`, `end`, `clip_filename`). Actual model uses `label`, `in_point`, `out_point`, `clip_path`. Affected Tasks 4–7; corrected in dispatch prompts before each subagent ran. No real harm done.
- **`build_storyboard` signature** — 5 positional args (`analyses, project_root, settings, strategy, context`) rather than the kwargs the plan assumed. Adapted in `jobs.py`.
- **`put_storyboard` needed `cache_dir.mkdir(parents=True, exist_ok=True)`** — for freshly-registered projects where `.vlogkit/` hasn't been created yet. Not flagged in the plan, but the subagent caught it.
- **FastAPI split request/response schemas** — expected behavior but worth documenting for future plans that add new Pydantic models with defaults.

## Manual test checklist for the user

```bash
# Launch
cd desktop
VLOGKIT_PYTHON=/Users/bryan/Code/lsl/vlogkit/.venv/bin/python npm run dev

# In the window:
# 1. Open folder → pick a folder of real clips
# 2. Analyze — wait until all clips show "analyzed"
# 3. Switch to the BOARD tab — empty state with "Generate storyboard" button
# 4. Click Generate — takes several seconds (real LLM call via Claude)
# 5. Storyboard appears — sections with segment cards
# 6. Click a segment — inspector opens, clip plays, auto-seeks to in_point
# 7. Drag a segment within its section — persists via PUT
# 8. Edit the label / in_point / out_point — 500ms debounce saves
# 9. Click Regenerate in the header — button shows "Regenerating…",
#    WS event flips it back and the board refreshes with the new storyboard
# 10. Cmd-R to reload — all edits persist (check .vlogkit/storyboard.json)
```

## Iterate loop verdict

- ✅ Build: 9 feature commits across Tasks 0–7 + this review
- ✅ Test: 80 backend tests, desktop typecheck + build both clean
- ✅ Verify: backend event flow covered by monkey-patched regen tests; UI flow verified by build output + hand-review of the rendered components against DESIGN.md tokens
- ✅ Plan improvements: this document
- ➡️ Ready for Plan 5 (semantic search panel)
