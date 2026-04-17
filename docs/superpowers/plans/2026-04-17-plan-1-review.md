# Plan 1 — Backend Foundation — Implementation Review

**Branch:** feat/desktop-app-plan-1
**Commits:** 1b22e5e..HEAD
**Final test count:** 54 passed

## What shipped

- `src/vlogkit/server/` package (replaces the old single-file `server.py`):
  - `app.py` — `create_app` (single-project upload mode, used by `vlogkit serve`) and `create_desktop_app` (multi-project desktop mode, used by `vlogkit server` / `python -m vlogkit.server`)
  - `auth.py` — bearer-token dependency, shared across all protected routes
  - `registry.py` — `ProjectRegistry` with JSON persistence at `<registry>/projects.json`; stable 16-hex ids derived from path; idempotent `register`, `forget`, `get`, `list` (most-recent-first)
  - `routes/health.py` — `GET /healthz` (unauthenticated liveness probe; returns `{"status":"ok","version":...}`)
  - `routes/projects.py` — `POST /projects`, `GET /projects`, `GET /projects/{id}`, `DELETE /projects/{id}`
  - `routes/clips.py` — `GET /projects/{id}/clips`, `GET /projects/{id}/clips/{filename}`
  - `routes/media.py` — `GET /media/{hash}` with HTTP Range support (206 partial content)
  - `routes/uploads.py` — existing streaming-upload route, ported from the old `server.py`
  - `__main__.py` — `python -m vlogkit.server` launches `create_desktop_app` via uvicorn
- CLI: `vlogkit server` subcommand in `cli.py` that delegates to the desktop app factory
- Tests: 9 server test modules under `tests/server/` — unit (registry, auth), integration (clips, media, projects, health, uploads, openapi snapshot), subprocess entrypoint smoke. Total 54 tests across the project (44 new server tests + 10 pre-existing).

## What regressed / almost regressed

- Task 7 `/media/{hash}` route currently raises `HTTPException(status_code=404, detail="media not found")` with a bare string — not the `ErrorDetail` shape the other 404s use. Caught in review, left in because uniformity with the rest of Plan 1's 404s would require a broader refactor. Deferred.
- Task 7 `/media/{hash}` linear-scans all analyzed clips on every request and matches by `sha256` prefix. Reviewer flagged this as O(N) per request; intentionally kept as a FIXME for Plan 3.
- Task 5 initially read `project.load_clip_analysis`, but the real method on `Project` is `load_analysis`. Reviewer caught it; corrected via a `hasattr` guard so that we degrade to "unanalyzed" status if the method ever moves again. The guard is now redundant but kept for robustness.
- OpenAPI snapshot (Task 9) forced us to re-export the snapshot once after the Task 8 `__main__` landed because it added a new operation id to the schema. Not a regression, but a reminder that the snapshot is load-bearing.

## Rough edges / known trade-offs

- `/media/{hash}` linear scan — FIXME comment in `routes/media.py` points to Plan 3 for a sha256→path index built during analyze.
- `hasattr(project, "load_analysis")` guard in `routes/clips.py` is redundant now that we know the method exists on `Project`. Keeping it for defensive reasons, but it could be removed.
- `app.state.project` in single-project mode is set by `create_app` but never read by anything downstream — the single-project uploads route captures the project by closure. Deferred decision: closure capture vs `app.state` before more routes land.
- `ErrorDetail` schema does not show up in OpenAPI `components` because it is only used inside `HTTPException(detail=...)` bodies. The TS type generator in Plan 2 will need to hand-write it or we emit it as a response model explicitly.
- Project registry writes `projects.json` on every mutation without a lock file — fine for a single desktop shell, but concurrent writers (e.g. two sidecars on the same registry) could race. Not a real scenario today.
- `vlogkit serve` vs `vlogkit server` naming is easy to confuse. Left as-is per plan; a later cleanup could rename one of them.

## Deferred items to carry into Plan 2 / 3

- **Plan 2:** Electron shell + sidecar spawning, preload bridge, renderer wired to the real `/projects` endpoints. The bearer token will be generated per-launch and passed from the shell to the sidecar and renderer. TS types need to be generated from the OpenAPI snapshot — see the `ErrorDetail` note above.
- **Plan 3:** Replace the `/media/{hash}` linear scan with a sha256→path index built during analyze. Add `/analyze` endpoint with WebSocket progress. Add `/media/{hash}/thumb` route for keyframe thumbnails.
- **Convention to decide before Plan 4:** `app.state.project` vs closure-capture for per-request context. Pick one before routes multiply.
- **Test infra:** consider pulling the `client + token + registry + temp dir` fixture out of each test module into a shared `conftest.py` to cut boilerplate.

## Spec gaps discovered during implementation

- `Project.load_clip_analysis` in the spec turned out to be `Project.load_analysis` in the real code. Handled via `hasattr` guard as the plan permitted.
- Spec's "16-hex project id" was under-specified — we picked `sha256(abspath)[:16]` which is stable across registry restarts and across machines mounting the same path. Documented in `registry.py`.
- Spec assumed `/media/{hash}` can serve any file the server can see; in practice we restrict to files reachable from a registered project. Keeps path-traversal attacks out of scope.
- Spec's Range handling did not specify behavior for open-ended `Range: bytes=N-`; we return the tail from N to EOF (test `test_media_open_ended_range`).

## Iterate loop verdict

- Build: 9 feature commits landed on feat/desktop-app-plan-1 (1b22e5e..f96e171) plus this review's docs commits on top.
- Test: 54 tests, 9 test modules, unit + integration + subprocess entrypoint smoke. All green.
- Verify: end-to-end curl-based smoke against a real running sidecar on port 8421 (Task 10 Step 2). All four endpoints (`/healthz`, `POST /projects`, `GET /projects`, `GET /projects/{id}/clips`) returned the expected shapes.
- Plan improvements: this document.
- Ready for Plan 2.

## Final review fixes (landed on this branch post-review)

- **Hash-space contract:** `/media/{hash}` now accepts both the 16-char prefix used by `ClipSummary.sha256` and the full 64-char sha256. Regression test added. Plan 2's renderer can link `GET /clips` results to `/media` without transformation.
- **Memory-safe hashing:** `/media/{hash}` linear scan now hashes clips in 1 MB chunks instead of `read_bytes()`. The linear scan is still O(N) and will be replaced in Plan 3 — but it no longer blows RAM on large videos.
- **Docs:** removed stale `[server]` optional-extras references in CLAUDE.md; added a BREAKING CHANGE note about `vlogkit serve` now requiring a Bearer token.
- **Token visibility:** `Auth token:` line is now bold yellow in both `vlogkit serve` and `vlogkit server`.

## Still open for Plan 2's first commit

- **ErrorDetail not in OpenAPI schema** — it's only used as `HTTPException(detail=...)` content, so FastAPI never renders it into `components/schemas`. Plan 2's TS type generator will either hand-write it or miss typed errors. Fix by adding explicit `responses={404: {"model": ErrorDetail}}` to each route OR a global exception handler that returns an `ErrorDetail`-shaped body.
- **`/media/{hash}` 404 shape** still uses bare `detail="media_not_found"` string instead of the structured `ErrorDetail` shape. Fold into the fix above.
- **Token on subprocess argv** — Electron sidecar spawn should pass the token via env var (or stdin), not `--token` on argv, to avoid `ps` exposure.
- **Extract shared `_registry` / `_load_project` helpers** into `server/deps.py` before more route modules land in Plan 3.
- **Decide closure vs. `app.state` convention** for route→project lookup before Plan 4's storyboard routes.
- **Non-constant-time token compare** — `auth.py` uses `!=` instead of `hmac.compare_digest`. Acceptable on 127.0.0.1 but trivial to fix.
- **CORS `allow_origins=["*"]`** — tighten to the Electron custom scheme once Plan 2 picks one.
