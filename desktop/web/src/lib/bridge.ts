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
