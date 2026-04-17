"use client";

import { useRouter } from "next/navigation";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { ProjectCard } from "./project-card";
import { EmptyState } from "./empty-state";

export function ProjectList() {
  const router = useRouter();
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
          onOpen={(id) => router.push(`/project?id=${id}&tab=clips`)}
          onForget={(id) => forget.mutate(id)}
        />
      ))}
    </div>
  );
}
