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
