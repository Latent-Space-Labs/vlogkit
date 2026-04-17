import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { startSidecar, type SidecarHandle } from "./sidecar";
import { createWindow, setupDockIcon } from "./window";

let sidecar: SidecarHandle | null = null;

async function bootstrap() {
  setupDockIcon();
  sidecar = await startSidecar(process.env.VLOGKIT_PYTHON ?? "python");

  // Preload reads process.env.VLOGKIT_API_PORT/TOKEN. Each BrowserWindow
  // inherits the main process env, so set them here before creating the window.
  process.env.VLOGKIT_API_PORT = String(sidecar.port);
  process.env.VLOGKIT_API_TOKEN = sidecar.token;

  ipcMain.handle("vlogkit:openFolder", async () => {
    const result = await dialog.showOpenDialog({
      properties: ["openDirectory"],
    });
    if (result.canceled || result.filePaths.length === 0) return null;
    return result.filePaths[0];
  });

  const devUrl = process.env.VLOGKIT_DEV_URL; // set by dev script
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
