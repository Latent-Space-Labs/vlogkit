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
    return win;
  }

  // Production / local-build mode: find index.html by trying both the
  // dev-server layout (electron/out/main/ -> ../../../web/out) and the
  // packaged-app layout (resources/web/out).
  const candidates = [
    join(__dirname, "../../../web/out/index.html"),
    join(process.resourcesPath, "web/out/index.html"),
  ];
  const htmlPath = candidates.find((p) => existsSync(p));
  if (!htmlPath) {
    throw new Error(
      "Could not locate web/out/index.html. Run `npm run build -w web` first.\n" +
        `Tried: ${candidates.join(", ")}`,
    );
  }
  win.loadFile(htmlPath);
  return win;
}

export function setupDockIcon() {
  if (process.platform === "darwin") {
    app.setName("vlogkit");
  }
}
