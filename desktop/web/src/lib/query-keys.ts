export const queryKeys = {
  projects: ["projects"] as const,
  project: (id: string) => ["projects", id] as const,
  clips: (projectId: string) => ["projects", projectId, "clips"] as const,
};
