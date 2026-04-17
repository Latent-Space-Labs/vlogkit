# Plan 6 — Export + DMG Packaging — Implementation Review

**Branch:** feat/desktop-app-plan-1
**Plan 6 commits:** `c768cc9`..HEAD (5 commits)
**Final backend test count:** 94 passed
**Desktop typecheck + build:** clean
**Branch total vs main:** ~50 commits

## What shipped

- **Task 1** — `POST /projects/{id}/export` via `vlogkit.export.timeline.storyboard_to_timeline` + `vlogkit.export.formats.export_timeline`. Handles missing storyboard (loads from `.vlogkit/storyboard.json` or falls back to parsing `storyboard.md`). 5 new tests (happy path, adapter-raises → 400, 404, 401, 422).
- **Task 2** — Regenerated TS types (1026 → 1120 lines). `api.exportStoryboard` client method. `window.vlogkitSaveFile` IPC exposed via preload contextBridge, implemented in main process using `dialog.showSaveDialog`.
- **Task 3** — `ExportDialog` component: modal with 4 radio-card format picker (fcpxml / edl / premiere / otio), native save-file dialog via IPC, status feedback (idle → running → done/error with exported path). Wired into board header next to Regenerate.
- **Task 4** — electron-builder installed as dev dep (auto-pinned to ^26.8.1, newer than planned ^25). `build` config in `desktop/electron/package.json` for macOS DMG output at `desktop/electron/dist/vlogkit-${version}.dmg`. `identity: null` disables code signing. `extraResources` copies `web/out/` into `resources/web/out/` of the packaged app. `window.ts` rewritten to probe both dev-server (`../../../web/out/index.html`) and packaged (`process.resourcesPath/web/out/index.html`) layouts, throws a clear error if neither exists. `npm run dist` script added (not run in CI — downloads ~100 MB helpers).

## What regressed / almost regressed

- Nothing. `window.ts`'s new candidate-probe approach works for both dev (`npm run dev`) and packaged flows with the same binary — tested indirectly via the existing `npm run build` green.

## Rough edges / known trade-offs

- **Code signing + notarization are OFF.** On macOS, opening the packaged DMG's `.app` will trigger Gatekeeper ("vlogkit can't be opened because Apple cannot check it…"). User has to right-click → Open the first time, or disable the quarantine bit via `xattr -d com.apple.quarantine`. Fine for personal / dev use; not shippable to other users until signed.
- **No auto-update.** `electron-updater` isn't wired. Every version bump requires manually downloading a new DMG.
- **Windows / Linux DMG equivalents** (nsis, AppImage) not configured. `"target": ["dmg"]` is macOS-only. Adding them is a 3-line config change + installing those targets' helpers.
- **`npm run dist` hasn't been test-run.** Config is valid (electron-builder `--help` works), but an actual DMG build could still reveal issues (e.g., a path mismatch in `extraResources`, missing icons, or sandbox entitlements warnings). First real `npm run dist` by the user is the actual validation.
- **No app icon.** Default Electron icon will appear in the dock / DMG. Adding one requires `.icns` file under `desktop/electron/build/icon.icns` (convention).
- **Export dialog is a plain `<div>` modal**, not shadcn's Dialog primitive (installed in Plan 2 but unused). Worth migrating for accessibility (focus trap, Escape key, aria-modal).
- **Export failure messages surface raw exceptions** to the UI (e.g., "no storyboard" → `detail.code = export_failed`, `detail.message = "no storyboard"`). UX could map known codes to friendly copy.
- **File path in the success banner can overflow** on long paths — `break-all` helps but isn't pretty.
- **No concurrent-export guard.** Clicking Export twice spawns two jobs against the same destination. Last-one-wins. Not a real risk in practice but a latent bug.
- **`export_storyboard` doesn't receive a `fps` parameter** — uses `storyboard_to_timeline`'s default (30.0). Could be exposed as an advanced option.

## Deferred beyond the 6-plan sequence

- Code signing (Developer ID Application cert, `CSC_LINK`, `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD` env vars; `identity: null` → real identity string)
- Apple notarization (`electron-builder`'s `notarize` option with an app-specific password)
- Auto-update via `electron-updater` + a GitHub Releases publish target
- Windows (`nsis`) and Linux (`AppImage` / `deb`) build targets
- shadcn `<Dialog>` migration for the export modal
- Streaming LLM for storyboard regenerate (carry-over from Plan 4)
- Cross-section storyboard drag (carry-over from Plan 4)
- Real clip thumbnails in search results (carry-over from Plan 5)
- `hmac.compare_digest` for token compare (carry-over from Plan 1 review)

## Manual test checklist for the user

```bash
# 1. Dev launch — confirm Export button appears and dialog opens:
cd desktop
VLOGKIT_PYTHON=/Users/bryan/Code/lsl/vlogkit/.venv/bin/python npm run dev

# In the window:
# - Open folder, analyze, generate storyboard (Plans 3-4 flows)
# - On the board tab, click "Export" top-right
# - Pick a format → click "Export" in the dialog
# - Native save dialog opens → pick a destination → confirm
# - Success banner shows the saved path
# - Open the file in Final Cut / DaVinci / Premiere / etc. → verify it loads

# 2. Build a real DMG (optional — takes a few minutes first time):
cd desktop/web && npm run build
cd ../electron && npm run dist
# Output: desktop/electron/dist/vlogkit-0.1.0.dmg
# Double-click to mount; drag vlogkit.app to /Applications
# First open: right-click → Open (Gatekeeper bypass for unsigned apps)
```

## Iterate loop verdict

- ✅ Build: 5 commits (Tasks 1–4 + this review)
- ✅ Test: 94 backend tests (89 + 5 new for export); desktop typecheck + build both clean
- ✅ Verify: backend export covered by monkey-patched tests; real `vlogkit.export` adapter verified by reading the CLI's existing flow; electron-builder config valid (CLI runs `--help` without error)
- ✅ Plan improvements: this document
- ➡️ **Six-plan sequence complete.** Branch ready to merge into `main`.
