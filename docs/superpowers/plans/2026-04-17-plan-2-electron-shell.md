# Desktop App — Plan 2: Electron Shell + Next.js Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a real Electron window that launches the Python sidecar, loads a Next.js UI, and lets the user open a folder as a project. The `desktop/` directory is new; Plan 1's backend is reused as-is.

**Architecture:** Electron Main (TypeScript) spawns `python -m vlogkit.server` as a sidecar with a random bearer token passed via env var. Next.js (App Router, static-export) runs as a child dev server in development (Electron loads `http://localhost:3456`) or is served from disk in production. A preload script exposes `window.vlogkit.apiPort` and `window.vlogkit.token` via `contextBridge`. Project picker page uses TanStack Query + the DESIGN.md token system.

**Tech Stack:** Electron 32, Next.js 15 (App Router, `output: 'export'`), React 19, TypeScript 5, Tailwind CSS 4, shadcn/ui, TanStack Query v5, dnd-kit (not used in this plan — added for later plans), `openapi-typescript` for generated API types, electron-vite for main/preload bundling, electron-builder for dev launching (no packaging yet — that's Plan 6).

---

## File Structure

**Backend tweaks (Task 0 only):**
- Modify: `src/vlogkit/server/__main__.py` — accept `VLOGKIT_TOKEN` env var as fallback for `--token`
- Modify: `src/vlogkit/server/routes/clips.py` — `/media/{hash}` 404 uses `ErrorDetail` shape
- Modify: `src/vlogkit/server/routes/projects.py`, `.../clips.py`, `.../uploads.py` — add `responses={4xx: {"model": ErrorDetail}}` so `ErrorDetail` lands in OpenAPI components
- Modify: `tests/server/snapshots/openapi.json` — regenerate via `VLOGKIT_UPDATE_SNAPSHOTS=1` after above change
- Add 1 test covering env-var token fallback

**New desktop app:**
```
desktop/
  package.json                    # workspace root; orchestrates electron + web
  tsconfig.json
  .gitignore
  electron/
    package.json
    tsconfig.json
    electron.vite.config.ts       # bundles main + preload
    src/
      main/
        index.ts                  # Electron main process
        sidecar.ts                # Python sidecar lifecycle
        window.ts                 # BrowserWindow creation
      preload/
        index.ts                  # contextBridge → window.vlogkit.{apiPort, token}
        types.ts                  # VlogkitBridge TS type (shared with renderer)
  web/
    package.json
    tsconfig.json
    next.config.ts                # output: 'export'
    postcss.config.mjs
    tailwind.config.ts
    components.json               # shadcn config
    public/
    src/
      app/
        layout.tsx
        page.tsx                  # project picker (recent + Open Folder)
        globals.css                # DESIGN.md tokens → Tailwind @theme
        providers.tsx              # TanStack Query provider
      components/
        ui/                        # shadcn primitives (button, card, etc.)
        projects/
          project-list.tsx
          project-card.tsx
          open-folder-button.tsx
          empty-state.tsx
      lib/
        api.ts                    # typed fetch client
        api-types.ts              # generated from OpenAPI (do not hand-edit)
        bridge.ts                 # thin wrapper over window.vlogkit
        query-keys.ts
  scripts/
    gen-api-types.sh              # runs openapi-typescript against a live sidecar
```

---

## Task 0: Backend tweaks for TS consumption

**Files:**
- Modify: `src/vlogkit/server/__main__.py`
- Modify: `src/vlogkit/server/routes/projects.py`, `.../clips.py`, `.../uploads.py`
- Modify: `tests/server/snapshots/openapi.json` (regenerated, not hand-edited)
- Modify: `tests/server/test_entrypoint.py` — add env-var token test

- [ ] **Step 1: Accept `VLOGKIT_TOKEN` env var in the sidecar entrypoint**

Edit `src/vlogkit/server/__main__.py`. Change `--token` from `required=True` to a default sourced from `os.environ.get("VLOGKIT_TOKEN")`:

```python
import os

def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m vlogkit.server")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--token",
        type=str,
        default=os.environ.get("VLOGKIT_TOKEN"),
        help="Bearer token. Falls back to VLOGKIT_TOKEN env var.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path.home() / ".vlogkit" / "projects.json",
    )
    parser.add_argument("--bind", type=str, default="127.0.0.1")
    args = parser.parse_args()

    if not args.token:
        parser.error("--token or VLOGKIT_TOKEN env var required")

    run_desktop_server(
        registry_path=args.registry,
        token=args.token,
        host=args.bind,
        port=args.port,
    )
```

- [ ] **Step 2: Write the env-var token test**

Append to `tests/server/test_entrypoint.py`:

```python
@pytest.mark.timeout(30)
def test_module_entrypoint_reads_token_from_env(tmp_path: Path) -> None:
    port = _free_port()
    token = "env-token-xyz"
    registry = tmp_path / "projects.json"

    env = os.environ.copy()
    env["VLOGKIT_TOKEN"] = token
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "vlogkit.server",
            "--port", str(port),
            "--registry", str(registry),
            "--bind", "127.0.0.1",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1.0)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)
        else:
            stdout, stderr = proc.communicate(timeout=2)
            pytest.fail(f"server never became ready. stdout={stdout!r} stderr={stderr!r}")

        r = httpx.get(
            f"http://127.0.0.1:{port}/projects",
            headers={"Authorization": f"Bearer {token}"},
            timeout=2,
        )
        assert r.status_code == 200
        assert r.json() == []
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
```

- [ ] **Step 3: Surface `ErrorDetail` in OpenAPI + fix `/media` error shape**

Edit the three route files so their error responses declare `ErrorDetail` as the response model. This makes `ErrorDetail` land in `components/schemas` of the OpenAPI doc — the TS generator will then produce a proper type for it.

In `src/vlogkit/server/routes/projects.py`, add `responses={404: {"model": ErrorDetail}}` to each decorator that can return 404:

```python
@router.post("", response_model=ProjectEntryResponse, status_code=status.HTTP_201_CREATED,
             responses={404: {"model": ErrorDetail}})
# ... and similarly for get_project and forget_project
```

In `src/vlogkit/server/routes/clips.py`, do the same for `list_clips`, `get_clip`, and `stream_media`. Also change `stream_media`'s 404 from bare string to structured:

```python
raise HTTPException(
    status_code=404,
    detail=ErrorDetail(
        code="media_not_found",
        message=f"No clip with hash {clip_hash} found in any registered project",
    ).model_dump(),
)
```

Import `ErrorDetail` at the top of `clips.py` if it isn't already.

- [ ] **Step 4: Update the `test_media_unknown_hash_returns_404` test to assert the structured shape**

In `tests/server/test_media.py`, the existing `test_media_unknown_hash_returns_404` only checks `status_code`. Tighten it:

```python
def test_media_unknown_hash_returns_404(
    desktop_client: TestClient, auth_headers: dict[str, str]
) -> None:
    resp = desktop_client.get(f"/media/{'0' * 64}", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "media_not_found"
```

- [ ] **Step 5: Regenerate the OpenAPI snapshot**

Run: `VLOGKIT_UPDATE_SNAPSHOTS=1 pytest tests/server/test_openapi_snapshot.py -v`

Expect: snapshot rewritten, test passes. Afterwards, `ErrorDetail` should appear in `components/schemas`:

```bash
python -c "import json; d=json.load(open('tests/server/snapshots/openapi.json')); assert 'ErrorDetail' in d['components']['schemas'], 'ErrorDetail missing from components'"
```

- [ ] **Step 6: Run full suite**

Run: `pytest -v`
Expect: **57 passed** (was 55: +1 env-var test, +1 stronger media-404 assertion counts as modifying an existing test, not adding a new one, so +1 from the env-var test only).

Correction: Step 4 modifies an existing test in place, so test count goes to **56 passed** (55 + 1 env-var).

- [ ] **Step 7: Commit**

```bash
git add src/vlogkit/server/__main__.py src/vlogkit/server/routes/ tests/server/test_entrypoint.py tests/server/test_media.py tests/server/snapshots/openapi.json
git commit -m "feat(server): env-var token fallback + ErrorDetail in OpenAPI schema (Plan 2 prep)"
```

---

## Task 1: Scaffold `desktop/` workspace

**Files:**
- Create: `desktop/package.json` (workspace root)
- Create: `desktop/.gitignore`
- Create: `desktop/tsconfig.json` (base config extended by electron + web)
- Create: `desktop/README.md`
- Modify: `.gitignore` at repo root — ignore `desktop/**/node_modules` and `desktop/web/out` and `desktop/electron/out`
- Modify: `CLAUDE.md` — add `desktop/` to Architecture section

- [ ] **Step 1: Create `desktop/.gitignore`**

```
node_modules/
**/dist/
**/out/
**/.next/
.turbo/
*.log
.env
.env.local
```

- [ ] **Step 2: Create `desktop/package.json`**

```json
{
  "name": "vlogkit-desktop",
  "version": "0.1.0",
  "private": true,
  "workspaces": ["electron", "web"],
  "scripts": {
    "dev": "concurrently -k -n web,electron -c auto \"npm run dev -w web\" \"npm run dev -w electron\"",
    "build": "npm run build -w web && npm run build -w electron",
    "gen:api": "bash scripts/gen-api-types.sh",
    "typecheck": "npm run typecheck -w web && npm run typecheck -w electron"
  },
  "devDependencies": {
    "concurrently": "^9.0.0",
    "typescript": "^5.6.0"
  }
}
```

- [ ] **Step 3: Create `desktop/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "preserve"
  }
}
```

- [ ] **Step 4: Append to repo-root `.gitignore`**

```
# desktop app
desktop/**/node_modules/
desktop/web/.next/
desktop/web/out/
desktop/electron/out/
```

- [ ] **Step 5: Update CLAUDE.md Architecture**

Add after the existing `Server` bullet:

```
- **Desktop** (`desktop/`): Electron shell + Next.js renderer. Two npm workspaces — `desktop/electron/` (TypeScript, main + preload) and `desktop/web/` (Next.js 15 static export, React 19, shadcn/ui + DESIGN.md tokens). Launched via `npm run dev` from `desktop/`; spawns `python -m vlogkit.server` as a sidecar with auth token passed via `VLOGKIT_TOKEN` env var.
```

- [ ] **Step 6: Commit**

```bash
git add desktop/ .gitignore CLAUDE.md
git commit -m "feat(desktop): scaffold desktop workspace"
```

---

## Task 2: Bootstrap Next.js web app

**Files:** everything under `desktop/web/` (created fresh)

- [ ] **Step 1: Init Next.js**

```bash
cd desktop
npx -y create-next-app@15 web \
  --typescript \
  --tailwind \
  --app \
  --src-dir \
  --eslint \
  --use-npm \
  --no-turbopack \
  --no-import-alias
```

(If `create-next-app` prompts, accept defaults. `--no-import-alias` keeps paths simple for this plan.)

- [ ] **Step 2: Configure static export**

Edit `desktop/web/next.config.ts`:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
```

- [ ] **Step 3: Install runtime deps**

```bash
cd desktop/web
npm install @tanstack/react-query@^5
npm install -D openapi-typescript
```

- [ ] **Step 4: Install and initialize shadcn/ui**

```bash
cd desktop/web
npx -y shadcn@latest init -d
# Then add primitives we'll need:
npx -y shadcn@latest add button card dialog
```

- [ ] **Step 5: Replace generated `globals.css` with DESIGN.md tokens**

Create `desktop/web/src/app/globals.css`:

```css
@import "tailwindcss";

@theme {
  /* Warm neutrals from DESIGN.md */
  --color-background: #ffffff;
  --color-background-alt: #f6f5f4;
  --color-foreground: rgba(0, 0, 0, 0.95);
  --color-muted: #615d59;
  --color-muted-strong: #31302e;
  --color-placeholder: #a39e98;
  --color-accent: #0075de;
  --color-accent-strong: #005bab;
  --color-accent-focus: #097fe8;
  --color-badge-bg: #f2f9ff;
  --color-badge-text: #097fe8;
  --color-border-whisper: rgba(0, 0, 0, 0.1);

  /* Typography */
  --font-sans: "Inter", -apple-system, system-ui, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, "Segoe UI Emoji", "Segoe UI Symbol";

  /* Radius scale */
  --radius-micro: 4px;
  --radius-standard: 8px;
  --radius-comfortable: 12px;
  --radius-large: 16px;
  --radius-pill: 9999px;

  /* Shadows (Notion's multi-layer whispers) */
  --shadow-card: rgba(0,0,0,0.04) 0px 4px 18px, rgba(0,0,0,0.027) 0px 2.025px 7.84688px, rgba(0,0,0,0.02) 0px 0.8px 2.925px, rgba(0,0,0,0.01) 0px 0.175px 1.04062px;
  --shadow-deep: rgba(0,0,0,0.01) 0px 1px 3px, rgba(0,0,0,0.02) 0px 3px 7px, rgba(0,0,0,0.02) 0px 7px 15px, rgba(0,0,0,0.04) 0px 14px 28px, rgba(0,0,0,0.05) 0px 23px 52px;
}

html, body {
  background: var(--color-background);
  color: var(--color-foreground);
  font-family: var(--font-sans);
  font-feature-settings: "lnum", "locl";
}

body {
  font-size: 16px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

/* Display scale (compressed letter-spacing at size) */
h1 { font-size: 48px; font-weight: 700; line-height: 1; letter-spacing: -1.5px; }
h2 { font-size: 26px; font-weight: 700; line-height: 1.23; letter-spacing: -0.625px; }
h3 { font-size: 22px; font-weight: 700; line-height: 1.27; letter-spacing: -0.25px; }
```

- [ ] **Step 6: Build and verify static export**

```bash
cd desktop/web
npm run build
```

Expect `desktop/web/out/index.html` to exist.

- [ ] **Step 7: Commit**

```bash
git add desktop/web
git commit -m "feat(desktop): bootstrap Next.js renderer with DESIGN.md theme"
```

---

## Task 3: Generate OpenAPI → TS types

**Files:**
- Create: `desktop/scripts/gen-api-types.sh`
- Create: `desktop/web/src/lib/api-types.ts` (generated output, committed)

- [ ] **Step 1: Write the generator script**

Create `desktop/scripts/gen-api-types.sh` (make executable: `chmod +x`):

```bash
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# Use the committed snapshot — no live sidecar needed.
SNAPSHOT="tests/server/snapshots/openapi.json"
if [[ ! -f "$SNAPSHOT" ]]; then
  echo "Missing $SNAPSHOT — run tests first to generate it." >&2
  exit 1
fi

OUT="desktop/web/src/lib/api-types.ts"
echo "Generating $OUT from $SNAPSHOT..."
npx --prefix desktop/web openapi-typescript "$SNAPSHOT" -o "$OUT"
echo "Done."
```

- [ ] **Step 2: Generate the types**

```bash
cd /Users/bryan/Code/lsl/vlogkit
bash desktop/scripts/gen-api-types.sh
```

Expect `desktop/web/src/lib/api-types.ts` to exist with `paths`, `operations`, `components` types. Visual check: search for `ProjectEntryResponse`, `ErrorDetail` — both should be present.

- [ ] **Step 3: Commit**

```bash
git add desktop/scripts/ desktop/web/src/lib/api-types.ts
git commit -m "feat(desktop): generate TS types from OpenAPI snapshot"
```

---

## Task 4: API client + bridge

**Files:**
- Create: `desktop/web/src/lib/bridge.ts` — reads `window.vlogkit`
- Create: `desktop/web/src/lib/api.ts` — typed fetch wrapper
- Create: `desktop/web/src/lib/query-keys.ts`
- Create: `desktop/web/src/app/providers.tsx` — TanStack Query provider
- Modify: `desktop/web/src/app/layout.tsx` — wrap children in `<Providers>`

- [ ] **Step 1: Create `desktop/web/src/lib/bridge.ts`**

```typescript
/**
 * Electron preload bridge. In the real app, `window.vlogkit` is populated
 * by electron/preload. In the Next.js dev server (no Electron), we fall
 * back to a dev-mode bridge that reads from localStorage so developers
 * can point the browser at an already-running sidecar for hot-reload UI work.
 */

export interface VlogkitBridge {
  apiPort: number;
  token: string;
}

declare global {
  interface Window {
    vlogkit?: VlogkitBridge;
  }
}

export function getBridge(): VlogkitBridge {
  if (typeof window === "undefined") {
    // SSR safety — will be rehydrated on client
    return { apiPort: 0, token: "" };
  }
  if (window.vlogkit) return window.vlogkit;

  // Dev fallback: read from localStorage so you can run `vlogkit server` in a
  // terminal, paste the token into localStorage, and iterate on the UI in
  // a normal browser without launching Electron.
  const port = Number(localStorage.getItem("vlogkit:port") ?? "0");
  const token = localStorage.getItem("vlogkit:token") ?? "";
  return { apiPort: port, token };
}
```

- [ ] **Step 2: Create `desktop/web/src/lib/api.ts`**

```typescript
import type { components, paths } from "./api-types";
import { getBridge } from "./bridge";

type Project = components["schemas"]["ProjectEntryResponse"];
type ClipSummary = components["schemas"]["ClipSummary"];
type ErrorDetail = components["schemas"]["ErrorDetail"];

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: ErrorDetail | string,
  ) {
    super(
      typeof detail === "string" ? detail : detail.message,
    );
  }
  get code(): string | undefined {
    return typeof this.detail === "object" ? this.detail.code : undefined;
  }
}

function baseUrl(): string {
  const { apiPort } = getBridge();
  if (!apiPort) throw new Error("vlogkit sidecar not ready (no port)");
  return `http://127.0.0.1:${apiPort}`;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { token } = getBridge();
  const resp = await fetch(`${baseUrl()}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
  });
  if (!resp.ok) {
    let detail: ErrorDetail | string = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail ?? detail;
    } catch {
      /* no JSON body */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const api = {
  listProjects: () => request<Project[]>("/projects"),
  registerProject: (path: string) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify({ path }),
    }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  forgetProject: (id: string) =>
    request<void>(`/projects/${id}`, { method: "DELETE" }),
  listClips: (projectId: string) =>
    request<ClipSummary[]>(`/projects/${projectId}/clips`),
};

export type { Project, ClipSummary, ErrorDetail };
```

- [ ] **Step 3: Create `desktop/web/src/lib/query-keys.ts`**

```typescript
export const queryKeys = {
  projects: ["projects"] as const,
  project: (id: string) => ["projects", id] as const,
  clips: (projectId: string) => ["projects", projectId, "clips"] as const,
};
```

- [ ] **Step 4: Create `desktop/web/src/app/providers.tsx`**

```tsx
"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 10_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
```

- [ ] **Step 5: Wrap layout**

Edit `desktop/web/src/app/layout.tsx` to render `<Providers>` around `children`:

```tsx
import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "vlogkit",
  description: "AI vlog assembly",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

- [ ] **Step 6: Typecheck**

```bash
cd desktop/web
npx tsc --noEmit
```

Expect: no errors.

- [ ] **Step 7: Commit**

```bash
git add desktop/web/src/lib desktop/web/src/app/providers.tsx desktop/web/src/app/layout.tsx
git commit -m "feat(desktop): api client, bridge, TanStack Query provider"
```

---

## Task 5: Project picker page

**Files:**
- Create: `desktop/web/src/components/projects/project-list.tsx`
- Create: `desktop/web/src/components/projects/project-card.tsx`
- Create: `desktop/web/src/components/projects/empty-state.tsx`
- Create: `desktop/web/src/components/projects/open-folder-button.tsx`
- Modify: `desktop/web/src/app/page.tsx` — hero + project list + open folder

- [ ] **Step 1: `empty-state.tsx`**

```tsx
export function EmptyState() {
  return (
    <div className="text-center py-24 px-8">
      <h2 className="text-2xl font-bold mb-3">No projects yet</h2>
      <p className="text-[var(--color-muted)] max-w-md mx-auto">
        Drop a folder of video clips to get started. vlogkit will scan,
        analyze, and turn them into a storyboard you can edit.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: `project-card.tsx`**

```tsx
import type { Project } from "@/lib/api";

export function ProjectCard({
  project,
  onOpen,
  onForget,
}: {
  project: Project;
  onOpen: (id: string) => void;
  onForget: (id: string) => void;
}) {
  const lastOpenedDate = new Date(project.last_opened * 1000);
  return (
    <div
      className="bg-white rounded-[12px] border border-[var(--color-border-whisper)] p-5 flex items-center justify-between transition hover:-translate-y-[1px]"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <button
        onClick={() => onOpen(project.id)}
        className="flex-1 text-left"
      >
        <div className="font-semibold text-lg">{project.name}</div>
        <div className="text-sm text-[var(--color-muted)] truncate">
          {project.path}
        </div>
        <div className="text-xs text-[var(--color-placeholder)] mt-1">
          Last opened {lastOpenedDate.toLocaleString()}
        </div>
      </button>
      <button
        onClick={() => onForget(project.id)}
        className="ml-4 text-sm text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
      >
        Forget
      </button>
    </div>
  );
}
```

- [ ] **Step 3: `open-folder-button.tsx`**

```tsx
"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

export function OpenFolderButton() {
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: async () => {
      // Prefer native dialog via preload if available; fall back to prompt.
      const win = window as typeof window & {
        vlogkitOpenFolder?: () => Promise<string | null>;
      };
      const path = win.vlogkitOpenFolder
        ? await win.vlogkitOpenFolder()
        : prompt("Folder path:");
      if (!path) return null;
      return api.registerProject(path);
    },
    onSuccess: (project) => {
      if (project) qc.invalidateQueries({ queryKey: queryKeys.projects });
    },
  });
  return (
    <button
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending}
      className="px-4 py-2 rounded-[4px] font-semibold text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60 transition"
    >
      {mutation.isPending ? "Opening…" : "Open folder"}
    </button>
  );
}
```

- [ ] **Step 4: `project-list.tsx`**

```tsx
"use client";

import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { ProjectCard } from "./project-card";
import { EmptyState } from "./empty-state";

export function ProjectList() {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.projects,
    queryFn: api.listProjects,
  });

  const forget = useMutation({
    mutationFn: (id: string) => api.forgetProject(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.projects }),
  });

  if (isLoading) {
    return (
      <p className="text-[var(--color-muted)] text-sm">Loading projects…</p>
    );
  }
  if (error) {
    return (
      <p className="text-red-600 text-sm">
        Could not reach sidecar: {String(error)}
      </p>
    );
  }
  if (!data || data.length === 0) return <EmptyState />;

  return (
    <div className="grid gap-3">
      {data.map((p) => (
        <ProjectCard
          key={p.id}
          project={p}
          onOpen={(id) => console.log("open project", id)}
          onForget={(id) => forget.mutate(id)}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 5: `src/app/page.tsx`**

```tsx
import { ProjectList } from "@/components/projects/project-list";
import { OpenFolderButton } from "@/components/projects/open-folder-button";

export default function HomePage() {
  return (
    <main className="max-w-3xl mx-auto px-8 py-16">
      <header className="flex items-end justify-between mb-10">
        <div>
          <h1>vlogkit</h1>
          <p className="text-[var(--color-muted)] mt-2 text-lg">
            Turn a folder of clips into an edited story.
          </p>
        </div>
        <OpenFolderButton />
      </header>
      <section className="bg-[var(--color-background-alt)] rounded-[16px] p-6">
        <ProjectList />
      </section>
    </main>
  );
}
```

- [ ] **Step 6: Build**

```bash
cd desktop/web
npm run build
```

Expect successful static export to `desktop/web/out/`.

- [ ] **Step 7: Dev-browser sanity check**

```bash
# In one terminal: start a real sidecar
.venv/bin/python -m vlogkit.server --port 8430 --token browser-dev-token --registry /tmp/vlogkit-browser.json

# In another: start the Next.js dev server
cd desktop/web && npm run dev
```

Open `http://localhost:3000`. In the browser console, set the bridge:

```js
localStorage.setItem("vlogkit:port", "8430");
localStorage.setItem("vlogkit:token", "browser-dev-token");
location.reload();
```

Expect: empty state. Click "Open folder" → prompt → enter a real folder path → it appears in the list → "Forget" removes it.

- [ ] **Step 8: Commit**

```bash
git add desktop/web/src
git commit -m "feat(desktop): project picker page with TanStack Query"
```

---

## Task 6: Electron main + preload

**Files:**
- Create: `desktop/electron/package.json`
- Create: `desktop/electron/tsconfig.json`
- Create: `desktop/electron/electron.vite.config.ts`
- Create: `desktop/electron/src/main/index.ts`
- Create: `desktop/electron/src/main/sidecar.ts`
- Create: `desktop/electron/src/main/window.ts`
- Create: `desktop/electron/src/preload/index.ts`
- Create: `desktop/electron/src/preload/types.ts`

- [ ] **Step 1: `electron/package.json`**

```json
{
  "name": "vlogkit-electron",
  "version": "0.1.0",
  "private": true,
  "main": "./out/main/index.js",
  "scripts": {
    "dev": "electron-vite dev",
    "build": "electron-vite build",
    "start": "electron .",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "electron": "^32.0.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "electron-vite": "^2.3.0",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: `electron/tsconfig.json`**

```json
{
  "extends": "../tsconfig.json",
  "compilerOptions": {
    "outDir": "./out",
    "noEmit": false,
    "module": "ESNext",
    "types": ["node"]
  },
  "include": ["src/**/*.ts"]
}
```

- [ ] **Step 3: `electron/electron.vite.config.ts`**

```typescript
import { defineConfig } from "electron-vite";

export default defineConfig({
  main: { build: { lib: { entry: "src/main/index.ts" } } },
  preload: { build: { lib: { entry: "src/preload/index.ts" } } },
});
```

- [ ] **Step 4: `electron/src/preload/types.ts`**

```typescript
export interface VlogkitBridge {
  apiPort: number;
  token: string;
}

export interface VlogkitIPC {
  openFolder: () => Promise<string | null>;
}
```

- [ ] **Step 5: `electron/src/preload/index.ts`**

```typescript
import { contextBridge, ipcRenderer } from "electron";
import type { VlogkitBridge, VlogkitIPC } from "./types";

const port = Number(process.env.VLOGKIT_API_PORT ?? "0");
const token = process.env.VLOGKIT_API_TOKEN ?? "";

const bridge: VlogkitBridge = { apiPort: port, token };
contextBridge.exposeInMainWorld("vlogkit", bridge);

const ipc: VlogkitIPC = {
  openFolder: () => ipcRenderer.invoke("vlogkit:openFolder"),
};
contextBridge.exposeInMainWorld("vlogkitOpenFolder", ipc.openFolder);
```

- [ ] **Step 6: `electron/src/main/sidecar.ts`**

```typescript
import { spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:net";
import { randomBytes } from "node:crypto";
import { homedir } from "node:os";
import { join } from "node:path";

export interface SidecarHandle {
  port: number;
  token: string;
  proc: ChildProcess;
  kill: () => void;
}

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.listen(0, "127.0.0.1", () => {
      const addr = srv.address();
      if (!addr || typeof addr === "string") {
        reject(new Error("could not pick port"));
        return;
      }
      const port = addr.port;
      srv.close(() => resolve(port));
    });
  });
}

async function waitForHealth(port: number, deadlineMs = 15_000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < deadlineMs) {
    try {
      const resp = await fetch(`http://127.0.0.1:${port}/healthz`);
      if (resp.ok) return;
    } catch {
      /* not ready yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`sidecar on port ${port} never became ready`);
}

export async function startSidecar(
  pythonBin: string = "python",
): Promise<SidecarHandle> {
  const port = await freePort();
  const token = randomBytes(24).toString("base64url");
  const registry = join(homedir(), ".vlogkit", "projects.json");

  const proc = spawn(
    pythonBin,
    ["-m", "vlogkit.server",
      "--port", String(port),
      "--registry", registry,
      "--bind", "127.0.0.1"],
    {
      env: { ...process.env, VLOGKIT_TOKEN: token },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  proc.stdout?.on("data", (d) => process.stderr.write(`[sidecar] ${d}`));
  proc.stderr?.on("data", (d) => process.stderr.write(`[sidecar:err] ${d}`));

  await waitForHealth(port);

  return {
    port,
    token,
    proc,
    kill: () => {
      if (proc.exitCode === null) {
        proc.kill("SIGTERM");
        setTimeout(() => {
          if (proc.exitCode === null) proc.kill("SIGKILL");
        }, 3000);
      }
    },
  };
}
```

- [ ] **Step 7: `electron/src/main/window.ts`**

```typescript
import { BrowserWindow, app } from "electron";
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
      additionalArguments: [
        `--vlogkit-api-port=${opts.port}`,
        `--vlogkit-api-token=${opts.token}`,
      ],
      // The preload reads these via process.env (set by spawn below).
    },
  });

  if (opts.devUrl) {
    win.loadURL(opts.devUrl);
  } else {
    win.loadFile(join(__dirname, "../../web/out/index.html"));
  }

  return win;
}

export function setupDockIcon() {
  if (process.platform === "darwin") {
    app.setName("vlogkit");
  }
}
```

- [ ] **Step 8: `electron/src/main/index.ts`**

```typescript
import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { startSidecar, type SidecarHandle } from "./sidecar";
import { createWindow, setupDockIcon } from "./window";

let sidecar: SidecarHandle | null = null;

async function bootstrap() {
  setupDockIcon();
  sidecar = await startSidecar(process.env.VLOGKIT_PYTHON ?? "python");

  // Preload reads process.env.VLOGKIT_API_PORT/TOKEN. Since each
  // BrowserWindow inherits the main process env, set them here.
  process.env.VLOGKIT_API_PORT = String(sidecar.port);
  process.env.VLOGKIT_API_TOKEN = sidecar.token;

  ipcMain.handle("vlogkit:openFolder", async () => {
    const result = await dialog.showOpenDialog({
      properties: ["openDirectory"],
    });
    if (result.canceled || result.filePaths.length === 0) return null;
    return result.filePaths[0];
  });

  const devUrl = process.env.VLOGKIT_DEV_URL; // set by concurrently dev mode
  createWindow({
    port: sidecar.port,
    token: sidecar.token,
    devUrl,
  });
}

app.whenReady().then(bootstrap);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
app.on("before-quit", () => {
  sidecar?.kill();
});
app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    bootstrap();
  }
});
```

- [ ] **Step 9: Install and build**

```bash
cd desktop
npm install   # installs workspace roots
cd electron && npm run build
```

Expect `desktop/electron/out/main/index.js` and `desktop/electron/out/preload/index.js` to exist.

- [ ] **Step 10: Commit**

```bash
git add desktop/electron desktop/package-lock.json
git commit -m "feat(desktop): Electron main + preload + sidecar spawner"
```

---

## Task 7: Dev launch script + smoke

**Files:**
- Modify: `desktop/electron/package.json` — dev script that sets `VLOGKIT_DEV_URL=http://localhost:3000`
- Modify: `desktop/package.json` — orchestrate `web dev` + `electron dev` via concurrently

- [ ] **Step 1: Update `desktop/electron/package.json`**

Replace the `scripts.dev` value with:

```json
"dev": "VLOGKIT_DEV_URL=http://localhost:3000 electron-vite dev"
```

Add `wait-on` to devDependencies:

```bash
cd desktop/electron
npm install -D wait-on
```

Change `dev` to wait for Next.js first:

```json
"dev": "wait-on http://localhost:3000 && VLOGKIT_DEV_URL=http://localhost:3000 electron-vite dev"
```

- [ ] **Step 2: Confirm `desktop/package.json` orchestrates correctly**

The root `dev` script uses `concurrently` — it should start `web` and `electron` together. Already scaffolded in Task 1 Step 2.

- [ ] **Step 3: Launch**

```bash
cd desktop
npm run dev
```

Expect:
1. Next.js dev server comes up on port 3000.
2. Electron waits for it, then spawns.
3. Electron launches Python sidecar on a random port.
4. Window opens showing the project picker page.
5. "Open folder" opens a native macOS/Windows folder dialog.
6. Picking a folder registers it and it appears in the list.

- [ ] **Step 4: Smoke test (documented in report)**

Click through:
1. App window opens
2. Empty state shows
3. Open folder → pick `/tmp/vlogkit-demo-clips`
4. Card appears
5. Click "Forget" → card disappears
6. Close window → app quits → sidecar SIGTERMed (check with `ps aux | grep vlogkit.server`)

- [ ] **Step 5: Commit**

```bash
git add desktop/electron/package.json desktop/electron/package-lock.json
git commit -m "feat(desktop): dev launch script with Next.js wait-on"
```

---

## Task 8: Plan 2 verification gate

**Files:**
- Create: `docs/superpowers/plans/2026-04-17-plan-2-review.md`

- [ ] **Step 1: Full backend test suite still green**

```bash
pytest -v
```

Expect: 56 passed (55 previous + 1 env-var token test from Task 0).

- [ ] **Step 2: TS typecheck**

```bash
cd desktop
npm run typecheck
```

Expect: no errors in either `web` or `electron`.

- [ ] **Step 3: Production build works**

```bash
cd desktop
npm run build
```

Expect: `desktop/web/out/index.html` and `desktop/electron/out/main/index.js` both produced, no errors.

- [ ] **Step 4: Write `docs/superpowers/plans/2026-04-17-plan-2-review.md`**

Use the same template as Plan 1's review doc:
- What shipped
- Rough edges / known trade-offs
- Deferred items → Plan 3 / later
- Spec gaps discovered
- Iterate loop verdict (all ✅)

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-04-17-plan-2-review.md
git commit -m "docs: plan 2 review + carry-over items"
```

---

## Self-Review Notes

**Spec coverage (spec § numbers):**
- §3 stack → Tasks 1–6 deliver Electron + Next.js + TanStack Query + shadcn + DESIGN.md tokens.
- §4 architecture — Electron main owns sidecar lifecycle → Task 6.
- §4.1 sidecar lifecycle — health-check polling, env-var token, SIGTERM-then-SIGKILL → Task 6 Steps 6–8.
- §5 frontend structure — project picker route done → Tasks 4–5. Board / clips / search routes are Plans 3–5.
- §6 backend routes — Task 0 tightens the three items needed for TS type generation to work cleanly.
- §9 visual design — globals.css theme tokens → Task 2 Step 5.
- §10 testing — backend `pytest` still green (56), frontend typecheck clean (Task 8).
- §11 iterate loop — Task 8's verification gate before writing Plan 3.

**Placeholder scan:** no TBD/TODO/"add appropriate X" handwaves. Every step has real code or commands.

**Type consistency:** `VlogkitBridge` shape matches across preload/types.ts and web/bridge.ts. `ApiError.detail` typed as `ErrorDetail | string` (string for legacy bare-string details that don't exist after Task 0). `api.*` methods return `components["schemas"][...]` shapes generated from the OpenAPI snapshot.
