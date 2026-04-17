import type { components } from "./api-types";
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
