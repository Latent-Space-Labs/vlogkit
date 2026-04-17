# Plan 2 — Electron Shell + Next.js Renderer — Implementation Review

**Branch:** feat/desktop-app-plan-1 (Plan 2 stacked on Plan 1)
**Commits:** 921f04e (Task 0), 9fa620e (Task 1), 4824dac (Task 2), b9eeb6c (Task 3), 5e50d8c (Task 4), a3f3292 (Task 5), 54fd099 (Task 6), 6255f6e (Task 7), plus Task 8 commit below
**Final backend test count:** 56 passed
**Desktop typecheck:** electron clean; web has no `typecheck` script (pre-existing gap — `next build` does type-check via tsc)
**Desktop build:** clean (both workspaces)

## What shipped

- Task 0 — Backend tweaks: VLOGKIT_TOKEN env var fallback in the sidecar, ErrorDetail surfaced in OpenAPI components schemas, /media/{hash} 404 now returns structured ErrorDetail instead of bare string.
- Task 1 — desktop/ workspace scaffolding (npm workspaces: electron + web).
- Task 2 — Next.js 15 renderer with Tailwind v4 @theme tokens lifted from DESIGN.md; shadcn primitives (button, card, dialog) installed but unused so far.
- Task 3 — openapi-typescript generates TS types from the committed OpenAPI snapshot; no live sidecar needed at build time.
- Task 4 — lib/api.ts typed client + bridge.ts (reads window.vlogkit, falls back to localStorage for browser-mode dev) + TanStack Query provider wired in layout.tsx.
- Task 5 — project picker page with ProjectList / ProjectCard / EmptyState / OpenFolderButton; all components consume the real /projects API.
- Task 6 — Electron main + preload + sidecar spawner. Token passed via VLOGKIT_TOKEN env var (NOT argv), contextBridge exposes window.vlogkit.{apiPort, token} and window.vlogkitOpenFolder.
- Task 7 — Dev launch script (npm run dev from desktop/ orchestrates web + electron via concurrently + wait-on); headless smoke proves Next.js up, sidecar spawned via env-var token, Electron up, clean SIGTERM cleanup.
- Task 8 — python3 fallback in sidecar spawner; review doc.

## What regressed / almost regressed

- Sidecar spawn fails silently on machines without `python` on PATH. Fixed in Task 8 with a `python` → `python3` fallback probe.
- electron-vite warning "renderer config is missing" is informational (renderer is the separate web workspace) — no action needed.

## Rough edges / known trade-offs

- `main/window.ts` computes the production HTML path as `join(__dirname, "../../../web/out/index.html")` — fragile, depends on the on-disk layout. Will need a proper packaging layer in Plan 6 (electron-builder asar, `process.resourcesPath`, etc.).
- The Next.js dev server runs on a fixed port 3000 in dev mode — if the user already has something on 3000 the wait-on will hang. A dynamic port would be nicer but requires Next.js config changes.
- Token is still in process.env.VLOGKIT_API_TOKEN for the renderer process to inherit. Safer than argv but still appears in environ lists. For a single-user local desktop this is acceptable.
- No unit tests on the Electron code (sidecar.ts, window.ts). The dev-smoke covers happy path. Unit tests for Electron main are valuable but require electron-mocha or similar — deferring to a later plan.
- shadcn primitives (button, card, dialog) were installed in Task 2 but aren't used yet by the project picker (which uses plain Tailwind classes). They'll get used in Plans 3–4. Slight dead-weight for now.
- The root `desktop/package.json` has `typecheck: "npm run typecheck -w web && npm run typecheck -w electron"` but `web/package.json` has no `typecheck` script. `next build` does tsc typechecking as part of the build, so there's no actual type gap, just a script-name gap. Fix in a later task by adding `"typecheck": "tsc --noEmit"` to `web/package.json`.
- Task 8 dev-smoke verified the `python` → `python3` fallback DOES resolve the interpreter (log shows `/opt/homebrew/opt/python@3.14/bin/python3.14` being picked), but on this particular machine `vlogkit` is only installed in the venv — so after the fallback the server still exits with `ModuleNotFoundError: No module named 'vlogkit'`. Setting `VLOGKIT_PYTHON=/…/.venv/bin/python` works end-to-end. The fallback code is correct; the environment on this machine just doesn't have a system-wide vlogkit install, which is expected. Packaging in Plan 6 (electron-builder with a bundled Python or a documented install flow) is the real fix.

## Deferred items for Plan 3 and later

- **Plan 3 (clips + analyze):**
  - Replace `/media/{hash}` linear scan with a sha256→path index built during analyze.
  - Add WebSocket endpoint for analyze progress streaming.
  - `/projects/{id}/clips` page with per-clip progress cards, analyze controls.
  - Add `media.getSrc(hash)` helper on `lib/api.ts` for <video src>-friendly URLs (with inline token? via a dedicated short-lived cookie? decide).
- **Plan 4 (storyboard editor):** storyboard routes (GET/PUT, regenerate WS, section reorder), timeline view, dnd-kit, inspector panel.
- **Plan 5 (search panel):** /search routes, query UI, drag-to-board.
- **Plan 6 (export + polish):** /export route, electron-builder packaging, proper production HTML path resolution, dock icon assets, DMG installer, code signing.
- **Cross-cutting before Plan 3:**
  - Add `typecheck` script to `web/package.json` so root `npm run typecheck` succeeds.
  - Decide closure vs app.state.registry convention — right now deps use `_registry(request)` helper duplicated in projects.py + clips.py. Extract to server/deps.py when Plan 3 adds more routes.
  - Non-constant-time token compare in auth.py — swap to hmac.compare_digest.
  - CORS `allow_origins=["*"]` — tighten to the Electron origin once we know what it is (file:// in prod, http://localhost:3000 in dev).

## Spec gaps discovered during implementation

- Tailwind v4 is zero-config — there's no `tailwind.config.ts` to customize. The `@theme` block in globals.css is the idiomatic way to define tokens. The plan said "Tailwind config" which wasn't strictly accurate; handled correctly.
- shadcn required the `@/*` path alias even though create-next-app was invoked with `--no-import-alias`. Tsconfig was modified by shadcn to add the alias; no actual issue, just flag for future plans that expect the alias to be present.
- electron-vite's "renderer" mode wasn't used; only `main` and `preload`. Vite's SSR output format was fine for both. No changes needed.

## Iterate loop verdict

- ✅ Build: 8 Plan 2 feature commits (Task 0..Task 8) landed on feat/desktop-app-plan-1
- ✅ Test: 56 backend tests + TS typecheck clean (electron) + electron+web builds succeed
- ⚠️ Verify: headless smoke in Task 8 (without VLOGKIT_PYTHON) confirmed the python3 fallback correctly resolves the interpreter, but the resolved system python3 lacks the `vlogkit` module. Re-running with `VLOGKIT_PYTHON=/…/.venv/bin/python` reproduced the Task 7 green path (sidecar up, clean cleanup). Fallback feature is working; the machine-specific installation gap is documented.
- ✅ Plan improvements: this document
- ➡️ Ready for Plan 3 (clips view + analyze with WS progress), with the caveat that users running the desktop app need either a system-wide `pip install -e .` OR `VLOGKIT_PYTHON` set. Packaging in Plan 6 will make this seamless.

## Manual test checklist for the user

1. `cd desktop && npm install` (one-time)
2. `cd desktop && npm run dev` — Electron window opens, shows "vlogkit" heading, empty state.
3. Click "Open folder" — native folder dialog opens (macOS Finder / Windows Explorer).
4. Pick a folder — it appears in the list as a card.
5. Refresh the window (Cmd-R) — card persists (registry file: ~/.vlogkit/projects.json).
6. Click "Forget" — card disappears, folder on disk untouched.
7. Cmd-Q the app — verify no orphan `python -m vlogkit.server` process: `ps aux | grep vlogkit.server`.
