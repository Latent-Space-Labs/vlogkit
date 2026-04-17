# Desktop App — Plan 6: Export + Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Add a UI export dialog (FCPXML / EDL / OTIO / Premiere XML) and make the app packageable as a macOS `.dmg` installer via electron-builder. Fixes the fragile production HTML path in `window.ts` on the way.

**Architecture:** Backend adds `/projects/{id}/export` that calls existing `vlogkit.export.*` modules and returns a local file path. Frontend opens a native save dialog (via IPC) and shows the exported path on success. electron-builder config lives in `desktop/electron/package.json`'s `build` field. **Code signing / notarization is out of scope** — unsigned DMG works on the dev's own Mac (Gatekeeper warning on first open), and full distribution is a separate exercise requiring an Apple Developer account.

---

## File Structure

**Backend:**
- Create: `src/vlogkit/server/routes/export.py`
- Modify: `src/vlogkit/server/schemas.py` — `ExportRequest`, `ExportResponse`
- Modify: `src/vlogkit/server/app.py` — register router
- Add: `tests/server/test_export.py`

**Frontend:**
- Modify: `desktop/web/src/lib/api.ts` — `exportStoryboard`
- Create: `desktop/web/src/components/board/export-dialog.tsx`
- Modify: `desktop/web/src/components/board/board.tsx` — add Export button
- Modify: `desktop/electron/src/main/window.ts` — fix production HTML path resolution
- Modify: `desktop/electron/src/main/index.ts` — `vlogkit:saveFile` IPC
- Modify: `desktop/electron/src/preload/index.ts` + `types.ts` — expose `saveFile`
- Modify: `desktop/electron/package.json` — add electron-builder config

---

## Task 1: Backend `/export` route

**Files:**
- Create: `src/vlogkit/server/routes/export.py`
- Modify: `src/vlogkit/server/schemas.py`
- Modify: `src/vlogkit/server/app.py`
- Add: `tests/server/test_export.py`

### Pre-work

Read `src/vlogkit/export/__init__.py` and its submodules. Find the real export function(s) — likely `export_storyboard(storyboard, format, destination)` or similar in one or more of `fcpxml.py`, `edl.py`, `otio.py`, `premiere.py`. Report what you found.

Also note what formats are supported — the CLI says `fcpxml | edl | premiere | otio`.

### Step 1: Extend `schemas.py`

```python
from typing import Literal as _Literal  # already imported, just confirm

ExportFormat = Literal["fcpxml", "edl", "premiere", "otio"]


class ExportRequest(BaseModel):
    format: ExportFormat
    destination: str  # absolute path where the file should be written


class ExportResponse(BaseModel):
    path: str
    format: ExportFormat
    size_bytes: int
```

### Step 2: Write `tests/server/test_export.py`

```python
"""Tests for /projects/{id}/export."""
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


def test_export_writes_file(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vlogkit.server.routes import export as export_route

    def fake_run(project, fmt: str, dest: Path) -> None:
        dest.write_text(f"<fake {fmt} export>")

    monkeypatch.setattr(export_route, "_do_export", fake_run)

    dest = tmp_path / "out.fcpxml"
    resp = desktop_client.post(
        f"/projects/{registered}/export",
        headers=auth_headers,
        json={"format": "fcpxml", "destination": str(dest)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["path"] == str(dest)
    assert body["format"] == "fcpxml"
    assert body["size_bytes"] > 0
    assert dest.exists()


def test_export_without_storyboard_returns_400(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vlogkit.server.routes import export as export_route

    def fake_run(project, fmt: str, dest: Path) -> None:
        raise ValueError("No storyboard to export")

    monkeypatch.setattr(export_route, "_do_export", fake_run)

    resp = desktop_client.post(
        f"/projects/{registered}/export",
        headers=auth_headers,
        json={"format": "fcpxml", "destination": str(tmp_path / "x.fcpxml")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "export_failed"


def test_export_unknown_project_404(
    desktop_client: TestClient, auth_headers: dict[str, str], tmp_path: Path
) -> None:
    resp = desktop_client.post(
        "/projects/deadbeefdeadbeef/export",
        headers=auth_headers,
        json={"format": "fcpxml", "destination": str(tmp_path / "x.fcpxml")},
    )
    assert resp.status_code == 404


def test_export_requires_auth(
    desktop_client: TestClient, registered: str, tmp_path: Path
) -> None:
    resp = desktop_client.post(
        f"/projects/{registered}/export",
        json={"format": "fcpxml", "destination": str(tmp_path / "x.fcpxml")},
    )
    assert resp.status_code == 401


def test_export_bad_format_returns_422(
    desktop_client: TestClient,
    auth_headers: dict[str, str],
    registered: str,
    tmp_path: Path,
) -> None:
    resp = desktop_client.post(
        f"/projects/{registered}/export",
        headers=auth_headers,
        json={"format": "invalid", "destination": str(tmp_path / "x")},
    )
    assert resp.status_code == 422
```

### Step 3: Implement `routes/export.py`

```python
"""/projects/{id}/export."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from vlogkit.project import Project
from vlogkit.server.auth import require_token
from vlogkit.server.deps import get_registry, load_project
from vlogkit.server.registry import ProjectRegistry
from vlogkit.server.schemas import ErrorDetail, ExportRequest, ExportResponse


def _do_export(project: Project, fmt: str, dest: Path) -> None:
    """Adapter — real call to vlogkit.export. Monkey-patchable in tests."""
    from vlogkit.export import <real_export_fn>  # ADAPT based on pre-work
    <real_export_fn>(project, fmt, dest)


def create_router() -> APIRouter:
    router = APIRouter(
        prefix="/projects/{project_id}",
        tags=["export"],
        dependencies=[Depends(require_token)],
    )

    @router.post(
        "/export",
        response_model=ExportResponse,
        responses={
            400: {"model": ErrorDetail},
            404: {"model": ErrorDetail},
        },
    )
    def export(
        project_id: str,
        body: ExportRequest,
        registry: ProjectRegistry = Depends(get_registry),
    ) -> ExportResponse:
        project = load_project(registry, project_id)
        dest = Path(body.destination).expanduser().resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            _do_export(project, body.format, dest)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=ErrorDetail(
                    code="export_failed",
                    message=str(exc),
                ).model_dump(),
            )
        return ExportResponse(
            path=str(dest),
            format=body.format,  # type: ignore[arg-type]
            size_bytes=dest.stat().st_size,
        )

    return router
```

Adapt the `from vlogkit.export import ...` call based on pre-work. If the export API requires loading the storyboard first (e.g., `export_storyboard(storyboard, ...)`), do that inside `_do_export`.

### Step 4: Register + run tests

`src/vlogkit/server/app.py`: `app.include_router(export_routes.create_router())`.

```
VLOGKIT_UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/server/test_openapi_snapshot.py -v
.venv/bin/pytest -v
```

Expect **94 passed** (89 + 5).

### Step 5: Commit

```bash
git add src/vlogkit/server/routes/export.py src/vlogkit/server/schemas.py src/vlogkit/server/app.py tests/server/test_export.py tests/server/snapshots/openapi.json
git commit -m "feat(server): add /projects/{id}/export route"
```

---

## Task 2: Frontend export API + save-file IPC

**Files:**
- Regenerate: `desktop/web/src/lib/api-types.ts`
- Modify: `desktop/web/src/lib/api.ts` — `exportStoryboard`
- Modify: `desktop/electron/src/preload/types.ts` + `index.ts` — expose `saveFile`
- Modify: `desktop/electron/src/main/index.ts` — add `vlogkit:saveFile` IPC handler

### Step 1: Regen types

```bash
bash desktop/scripts/gen-api-types.sh
```

### Step 2: `api.ts`

Type alias:
```typescript
type ExportRequest = components["schemas"]["ExportRequest"];
type ExportResponse = components["schemas"]["ExportResponse"];
type ExportFormat = ExportRequest["format"];
```

Method:
```typescript
exportStoryboard: (projectId: string, req: ExportRequest) =>
  request<ExportResponse>(`/projects/${projectId}/export`, {
    method: "POST",
    body: JSON.stringify(req),
  }),
```

Re-exports: add `ExportRequest`, `ExportResponse`, `ExportFormat`.

### Step 3: Preload `saveFile`

Append to `desktop/electron/src/preload/types.ts`:

```typescript
export interface VlogkitIPC {
  openFolder: () => Promise<string | null>;
  saveFile: (opts: {
    defaultName: string;
    filters?: { name: string; extensions: string[] }[];
  }) => Promise<string | null>;
}
```

Extend `desktop/electron/src/preload/index.ts`:

```typescript
// after the existing window.vlogkitOpenFolder exposure:
contextBridge.exposeInMainWorld(
  "vlogkitSaveFile",
  (opts: Parameters<VlogkitIPC["saveFile"]>[0]) =>
    ipcRenderer.invoke("vlogkit:saveFile", opts),
);
```

### Step 4: Main IPC handler

Edit `desktop/electron/src/main/index.ts`. After the existing `ipcMain.handle("vlogkit:openFolder", ...)` block, add:

```typescript
ipcMain.handle("vlogkit:saveFile", async (_, opts: {
  defaultName: string;
  filters?: { name: string; extensions: string[] }[];
}) => {
  const result = await dialog.showSaveDialog({
    defaultPath: opts.defaultName,
    filters: opts.filters,
  });
  if (result.canceled || !result.filePath) return null;
  return result.filePath;
});
```

### Step 5: Rebuild electron + typecheck web

```bash
cd desktop/electron && npm run build
cd ../web && npx tsc --noEmit && npm run build
```

### Step 6: Commit

```bash
git add desktop/web/src/lib desktop/electron
git commit -m "feat(desktop): export API + saveFile IPC"
```

---

## Task 3: Export dialog UI

**Files:**
- Create: `desktop/web/src/components/board/export-dialog.tsx`
- Modify: `desktop/web/src/components/board/board.tsx`

### Step 1: `export-dialog.tsx`

```tsx
"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type ExportFormat } from "@/lib/api";

const FORMATS: {
  value: ExportFormat;
  label: string;
  ext: string;
  desc: string;
}[] = [
  { value: "fcpxml", label: "Final Cut Pro XML", ext: "fcpxml", desc: "Final Cut / DaVinci Resolve" },
  { value: "edl", label: "EDL", ext: "edl", desc: "Classic edit decision list" },
  { value: "premiere", label: "Premiere XML", ext: "xml", desc: "Premiere Pro" },
  { value: "otio", label: "OpenTimelineIO", ext: "otio", desc: "OTIO reference format" },
];

export function ExportDialog({
  projectId,
  projectName,
  onClose,
}: {
  projectId: string;
  projectName: string;
  onClose: () => void;
}) {
  const [format, setFormat] = useState<ExportFormat>("fcpxml");
  const [status, setStatus] = useState<
    | { kind: "idle" }
    | { kind: "running" }
    | { kind: "done"; path: string }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  const mutation = useMutation({
    mutationFn: async () => {
      const spec = FORMATS.find((f) => f.value === format)!;
      const pickSave = (window as typeof window & {
        vlogkitSaveFile?: (opts: {
          defaultName: string;
          filters?: { name: string; extensions: string[] }[];
        }) => Promise<string | null>;
      }).vlogkitSaveFile;
      const destination = pickSave
        ? await pickSave({
            defaultName: `${projectName}.${spec.ext}`,
            filters: [{ name: spec.label, extensions: [spec.ext] }],
          })
        : prompt(
            `Save path (${spec.ext}):`,
            `${projectName}.${spec.ext}`,
          );
      if (!destination) return null;
      setStatus({ kind: "running" });
      const res = await api.exportStoryboard(projectId, {
        format,
        destination,
      });
      return res;
    },
    onSuccess: (res) => {
      if (res) setStatus({ kind: "done", path: res.path });
    },
    onError: (err) => {
      setStatus({ kind: "error", message: String(err) });
    },
  });

  return (
    <div
      className="fixed inset-0 z-20 flex items-center justify-center bg-black/20"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-[16px] p-6 w-[480px] max-w-full"
        style={{ boxShadow: "var(--shadow-deep)" }}
      >
        <h3 className="text-lg font-bold mb-4">Export storyboard</h3>
        <div className="space-y-2 mb-4">
          {FORMATS.map((f) => (
            <label
              key={f.value}
              className={
                "flex items-start gap-3 p-3 rounded-[8px] border cursor-pointer transition " +
                (format === f.value
                  ? "border-[var(--color-accent)] bg-[var(--color-badge-bg)]"
                  : "border-[var(--color-border-whisper)] hover:border-[var(--color-muted)]")
              }
            >
              <input
                type="radio"
                name="format"
                value={f.value}
                checked={format === f.value}
                onChange={() => setFormat(f.value)}
                className="mt-1"
              />
              <div>
                <div className="font-semibold text-sm">{f.label}</div>
                <div className="text-xs text-[var(--color-muted)]">
                  .{f.ext} · {f.desc}
                </div>
              </div>
            </label>
          ))}
        </div>
        {status.kind === "done" ? (
          <p className="text-sm text-green-700 mb-4 break-all">
            ✓ Exported to {status.path}
          </p>
        ) : status.kind === "error" ? (
          <p className="text-sm text-red-600 mb-4">Error: {status.message}</p>
        ) : null}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-[4px] text-sm text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
          >
            Close
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || status.kind === "running"}
            className="px-4 py-1.5 rounded-[4px] font-semibold text-sm text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60"
          >
            {mutation.isPending || status.kind === "running"
              ? "Exporting…"
              : "Export"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

### Step 2: Wire into `board.tsx`

Add state + button + dialog render. Near the existing `regenInFlight` state:

```tsx
const [exportOpen, setExportOpen] = useState(false);
```

Replace the existing header's right-side `<RegenerateButton ... />` with a flex row containing both buttons:

```tsx
<div className="flex gap-2">
  <button
    onClick={() => setExportOpen(true)}
    className="px-3 py-1.5 rounded-[4px] font-semibold text-sm text-[var(--color-foreground)] border border-[var(--color-border-whisper)] bg-white hover:border-[var(--color-muted)]"
  >
    Export
  </button>
  <RegenerateButton projectId={projectId} inFlight={regenInFlight} />
</div>
```

At the bottom of the `Board` return (outside `<DndContext>` but inside the component return tree — e.g., wrap the whole thing in a fragment):

```tsx
{exportOpen ? (
  <ExportDialog
    projectId={projectId}
    projectName={data.title || "storyboard"}
    onClose={() => setExportOpen(false)}
  />
) : null}
```

Add imports: `ExportDialog`.

### Step 3: Typecheck + build

```bash
cd desktop/web && npx tsc --noEmit && npm run build
```

### Step 4: Commit

```bash
git add desktop/web/src/components/board
git commit -m "feat(desktop): storyboard export dialog with format picker"
```

---

## Task 4: Fix production HTML path + electron-builder setup

**Files:**
- Modify: `desktop/electron/src/main/window.ts` — robust production HTML resolution
- Modify: `desktop/electron/package.json` — `build` config for electron-builder

### Step 1: Install electron-builder

```bash
cd desktop/electron
npm install -D electron-builder
```

### Step 2: Fix `window.ts` production path

Current code: `win.loadFile(join(__dirname, "../../../web/out/index.html"))` — works for `npm run dev` (because `__dirname` is inside `desktop/electron/out/main/`) but NOT inside a packaged asar. Fix to read from app resources:

```typescript
import { BrowserWindow, app } from "electron";
import { existsSync } from "node:fs";
import { join } from "node:path";

export function createWindow(opts: {
  port: number;
  token: string;
  devUrl?: string;
}): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    backgroundColor: "#ffffff",
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (opts.devUrl) {
    win.loadURL(opts.devUrl);
  } else {
    // In dev/local builds, web/out is a sibling of electron/out.
    // In a packaged app, electron-builder copies web/out under
    // resources/app.asar.unpacked/web/out (see extraResources below).
    const candidates = [
      join(__dirname, "../../../web/out/index.html"),      // dev: desktop/electron/out/main/ → ../../../web/out/
      join(process.resourcesPath, "web/out/index.html"),   // packaged
    ];
    const htmlPath = candidates.find((p) => existsSync(p));
    if (!htmlPath) {
      throw new Error(
        "Could not locate web/out/index.html. Run `npm run build -w web` first.",
      );
    }
    win.loadFile(htmlPath);
  }

  return win;
}

export function setupDockIcon() {
  if (process.platform === "darwin") {
    app.setName("vlogkit");
  }
}
```

### Step 3: Add `build` config to `desktop/electron/package.json`

Add a `build` field:

```json
"build": {
  "appId": "ai.vlogkit.desktop",
  "productName": "vlogkit",
  "directories": {
    "output": "dist"
  },
  "files": [
    "out/**/*",
    "package.json"
  ],
  "extraResources": [
    {
      "from": "../web/out",
      "to": "web/out"
    }
  ],
  "mac": {
    "category": "public.app-category.video",
    "target": ["dmg"],
    "identity": null
  },
  "dmg": {
    "artifactName": "vlogkit-${version}.dmg"
  }
}
```

`"identity": null` disables code signing — fine for local unsigned builds. A future user with an Apple Developer ID can remove this to enable signing.

Add an npm script to the same file:

```json
"dist": "electron-vite build && electron-builder --mac --publish=never"
```

### Step 4: Verify build succeeds

```bash
cd desktop/web && npm run build
cd ../electron && npm run build   # electron-vite
```

DO NOT actually run `npm run dist` — it downloads electron-builder helpers (~100 MB), takes a while, and produces a DMG we won't use in CI. Just verify the config is valid by running:

```bash
cd desktop/electron
npx electron-builder --help 2>&1 | head -5
```

If that runs without error, electron-builder is installed and the config is at least parsable.

### Step 5: Commit

```bash
git add desktop/electron/package.json desktop/electron/src/main/window.ts desktop/package-lock.json desktop/electron/package-lock.json 2>/dev/null
git commit -m "feat(desktop): electron-builder DMG config + robust production HTML path"
```

---

## Task 5: Verification + Plan 6 review

- [ ] Full backend suite: `.venv/bin/pytest -v` → **94 passed**.
- [ ] Full desktop build: `cd desktop && npm run build` → green.
- [ ] Dev launch smoke: `cd desktop && VLOGKIT_PYTHON=/path/to/.venv/bin/python npm run dev` — confirm app launches, Export button appears on board header, clicking it shows the dialog.
- [ ] Write `docs/superpowers/plans/2026-04-17-plan-6-review.md` summarizing what shipped + what's deferred (code signing, notarization, auto-update, DMG actually produced).
- [ ] Final commit: the review doc.

---

## Self-Review Notes

- Code signing + notarization are explicitly deferred — require Apple Developer credentials the user may not have. Unsigned DMG works for personal use.
- No `electron-updater` auto-update wiring — another Apple-infra-dependent piece.
- Task 1's `_do_export` adapter is monkey-patchable for fast tests; real call happens in prod.
- Task 4's `candidates` array lets the same binary work for `npm run dev` AND packaged DMG without conditional branching on `app.isPackaged`.
