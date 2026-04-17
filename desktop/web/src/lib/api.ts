import type { components } from "./api-types";
import { getBridge } from "./bridge";

type Project = components["schemas"]["ProjectEntryResponse"];
type ClipSummary = components["schemas"]["ClipSummary"];
type ErrorDetail = components["schemas"]["ErrorDetail"];
type Storyboard = components["schemas"]["Storyboard-Output"];
type StoryboardInput = components["schemas"]["Storyboard-Input"];
type StoryboardSection = components["schemas"]["StoryboardSection"];
type StoryboardSegment = components["schemas"]["StoryboardSegment"];
type SearchHit = components["schemas"]["SearchHit"];
type SearchResponse = components["schemas"]["SearchResponse"];
type IndexStatus = components["schemas"]["IndexStatus"];
type ExportRequest = components["schemas"]["ExportRequest"];
type ExportResponse = components["schemas"]["ExportResponse"];
type ExportFormat = ExportRequest["format"];

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
  startAnalyze: (projectId: string) =>
    request<{ job_id: string }>(`/projects/${projectId}/analyze`, {
      method: "POST",
    }),
  getStoryboard: (projectId: string) =>
    request<Storyboard>(`/projects/${projectId}/storyboard`),
  putStoryboard: (projectId: string, storyboard: StoryboardInput) =>
    request<Storyboard>(`/projects/${projectId}/storyboard`, {
      method: "PUT",
      body: JSON.stringify(storyboard),
    }),
  regenerateStoryboard: (projectId: string) =>
    request<{ job_id: string }>(
      `/projects/${projectId}/storyboard/regenerate`,
      { method: "POST" },
    ),
  searchClips: (projectId: string, query: string, k = 10) =>
    request<SearchResponse>(
      `/projects/${projectId}/search?q=${encodeURIComponent(query)}&k=${k}`,
    ),
  buildSearchIndex: (projectId: string) =>
    request<{ job_id: string }>(`/projects/${projectId}/search/index`, {
      method: "POST",
    }),
  getIndexStatus: (projectId: string) =>
    request<IndexStatus>(`/projects/${projectId}/search/index`),
  exportStoryboard: (projectId: string, req: ExportRequest) =>
    request<ExportResponse>(`/projects/${projectId}/export`, {
      method: "POST",
      body: JSON.stringify(req),
    }),
};

export function getMediaUrl(hash: string): string {
  const { apiPort, token } = getBridge();
  return `http://127.0.0.1:${apiPort}/media/${hash}?token=${encodeURIComponent(token)}`;
}

export type {
  Project,
  ClipSummary,
  ErrorDetail,
  Storyboard,
  StoryboardSection,
  StoryboardSegment,
  SearchHit,
  SearchResponse,
  IndexStatus,
  ExportRequest,
  ExportResponse,
  ExportFormat,
};
