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
    },
  });

  if (opts.devUrl) {
    win.loadURL(opts.devUrl);
  } else {
    win.loadFile(join(__dirname, "../../../web/out/index.html"));
  }

  return win;
}

export function setupDockIcon() {
  if (process.platform === "darwin") {
    app.setName("vlogkit");
  }
}
