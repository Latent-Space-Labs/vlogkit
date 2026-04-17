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
