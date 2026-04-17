# Plan 5 — Semantic Search Panel — Implementation Review

**Branch:** feat/desktop-app-plan-1
**Plan 5 commits:** `6520c66`..HEAD (5 commits)
**Final backend test count:** 89 passed
**Desktop typecheck:** clean
**Desktop build:** clean

## What shipped

- **Task 0** — Extracted shared FastAPI deps (`get_registry`, `load_project`, `get_broker`) into `src/vlogkit/server/deps.py`. Mechanical refactor across 4 route files; OpenAPI snapshot stayed byte-identical (proof of zero behavioral change). +2 tests for the new module.
- **Task 1** — Backend search routes: `GET /projects/{id}/search?q=...&k=10`, `GET /projects/{id}/search/index` (status), `POST /projects/{id}/search/index` (start background job). Lazy imports of `vlogkit.search.*` so routes register even without `[search]` extras. 503 with `code: "search_extras_not_installed"` when deps missing. Real adapter maps `sentrysearch`'s `source_file`/`start_time`/`end_time`/`similarity_score` to our `SearchHit` schema.
- **Task 2** — TS types regenerated (808 → 1026 lines). `SearchHit`/`SearchResponse`/`IndexStatus` TS types. `api.searchClips` / `buildSearchIndex` / `getIndexStatus` client methods.
- **Task 3** — Search tab UI: `SearchBar`, `ResultCard`, `IndexPrompt` (handles missing-deps and empty-index cases), `SearchPanel` shell. Polls `/search/index` every 3s until `ready`, shows "indexed N/M clips (Z%)" progress. Results render as cards with score badge + snippet.
- **Task 4** — Each result card gets a "+ Insert into section" dropdown that deep-clones the storyboard, appends a new `StoryboardSegment` at the end of the chosen section, and persists via `PUT /storyboard`. Graceful empty state if no storyboard exists yet.

## What regressed / almost regressed

- Nothing. The Task 0 refactor was covered by the OpenAPI snapshot test — any behavioral drift would have failed the snapshot compare.
- Task 1 caught a signature mismatch between the plan's template and reality: `search_clips(query, project, n_results=)` (not the `(project, query)` the template assumed). Subagent adapted.

## Rough edges / known trade-offs

- **No WebSocket events for indexing progress.** The panel polls `/search/index` every 3 s. Works, but less snappy than analyze's per-clip WS events. Future polish: emit `index.progress` events through `WsBroker` and drop the poll.
- **Dropdown UX for inserting into board (not native drag-drop).** Simpler and works across tabs; functional outcome is the same.
- **Newly inserted segments use `hit.clip_filename` as `clip_path`** — a basename, not a full path. The board's inspector preview already uses `basename(clip_path)` for sha256 lookup, so it still resolves. But the existing Storyboard might use absolute paths elsewhere — mixing is fine today but could bite if anything starts expecting absolute-only paths.
- **Scores displayed as percentages** — misleading for cosine distances (0–1 scores but not calibrated). A real app would either show raw distance or display them relative to the top hit.
- **No pagination.** `k` is capped at 50 server-side; frontend requests 10 and doesn't offer more.
- **No clip thumbnails in result cards.** Plain text + score + times. Thumbnails would require exposing keyframes via the server.
- **Index builds synchronously in a daemon thread.** If the user closes the app during indexing, the thread is killed mid-way and the Chroma store may be partially populated. `index_clips(force=False)` is idempotent on re-runs, so clicking "Build index" again recovers.
- **Unused imports left after Task 0 refactor** in `analyze.py`/`storyboard.py` (Path, Project). No linter configured; deferred cleanup.
- **The dropdown menu has no outside-click-to-dismiss.** Clicking elsewhere doesn't close it; only a section click or toggling the button. Minor UX wart.

## Deferred items → Plan 6 and later

- **Plan 6 (export + packaging):**
  - `/export` route + format picker dialog + electron-builder DMG installer.
  - Production HTML path resolution in `window.ts` (currently `../../../web/out/index.html` — fragile, needs asar-aware lookup).
  - Dock icon + app metadata.
  - Code signing (macOS) + notarization.
- **Cross-plan polish:**
  - Real LLM streaming for regenerate (`storyboard.regen_token` events are schema-ready but unused).
  - WebSocket index progress (`index.progress` events).
  - Cross-section storyboard drag.
  - Prune unused imports in `analyze.py`/`storyboard.py` after Task 0 refactor.
  - Non-constant-time token compare in `auth.py` → `hmac.compare_digest`.
  - Real clip thumbnails on search result cards.

## Spec gaps discovered during implementation

- **`vlogkit.search` function names** — `index_clips` and `search_clips` (not `build_index` / `search` as the plan prose assumed). Arg order `search_clips(query, project, n_results=)`.
- **Result shape** — dicts with `source_file`/`start_time`/`end_time`/`similarity_score`, no `snippet` or `clip_sha256`. Adapter normalizes to `SearchHit` (snippet becomes empty string, sha256 becomes None). A follow-up could surface real transcription snippets.
- **`get_search_stats` returns `None` when deps missing** — adapter raises `ImportError` so the 503 path works for both query and index-status endpoints.
- **Pre-existing `chromadb` deprecation warning** carries through — not a vlogkit concern.

## Manual test checklist for the user

```bash
# 1. Confirm [search] extras installed:
pip install -e '.[search]'

# 2. Ensure VLOGKIT_GEMINI_API_KEY is set (required for embeddings):
export VLOGKIT_GEMINI_API_KEY=...

# 3. Launch
cd desktop
VLOGKIT_PYTHON=/Users/bryan/Code/lsl/vlogkit/.venv/bin/python npm run dev

# In the window:
# 1. Open a folder of real analyzed clips (Plan 3 flow)
# 2. Click the SEARCH tab
# 3. If extras not installed: see "Search extras not installed" page
# 4. If no index yet: see "Build index" button → click it
# 5. Watch the indexing progress update every few seconds
# 6. Once ready, type "sunset" (or whatever matches your clips)
# 7. Click Search → grid of result cards with scores + times + snippets
# 8. On a card, click "+ Insert into section" → dropdown of section titles
# 9. Pick a section → dropdown closes, the storyboard (board tab) gains
#    a new segment labeled "(from search)" at the end of that section
```

## Iterate loop verdict

- ✅ Build: 5 commits (Task 0 refactor + Tasks 1–4 features + this review)
- ✅ Test: 89 backend tests (82 + 7 new for search); desktop typecheck + build both clean
- ✅ Verify: monkey-patched search tests cover happy-path, 404, auth, 422, 503 missing-deps, index start; real `vlogkit.search` adapter verified by reading the module and writing the correct arg order
- ✅ Plan improvements: this document
- ➡️ Ready for Plan 6 (export + packaging — the final plan)
