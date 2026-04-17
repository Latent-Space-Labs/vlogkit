"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { connectEventStream } from "@/lib/ws";
import type { AnalyzeEvent, AnalyzeProgress } from "@/lib/events";
import { ClipCard } from "./clip-card";
import { AnalyzeButton } from "./analyze-button";

export function ClipsTab({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.clips(projectId),
    queryFn: () => api.listClips(projectId),
  });
  const [progress, setProgress] = useState<Record<string, AnalyzeProgress>>({});

  useEffect(() => {
    const disconnect = connectEventStream(projectId, (evt: AnalyzeEvent) => {
      if (evt.type === "analyze.progress") {
        setProgress((p) => ({ ...p, [evt.clip_filename]: evt }));
      } else if (evt.type === "analyze.clip_done") {
        setProgress((p) => {
          const { [evt.clip_filename]: _, ...rest } = p;
          return rest;
        });
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      } else if (evt.type === "analyze.clip_failed") {
        // Remove progress entry; list refetch will show whatever status the API returns.
        setProgress((p) => {
          const { [evt.clip_filename]: _, ...rest } = p;
          return rest;
        });
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      } else if (evt.type === "analyze.complete") {
        setProgress({});
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      }
    });
    return disconnect;
  }, [projectId, qc]);

  if (isLoading) return <p className="text-[var(--color-muted)]">Loading clips…</p>;
  if (error) return <p className="text-red-600">Error: {String(error)}</p>;
  if (!data || data.length === 0) {
    return (
      <p className="text-[var(--color-muted)] py-12 text-center">
        No clips in this folder.
      </p>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-[var(--color-muted)]">{data.length} clips</p>
        <AnalyzeButton projectId={projectId} />
      </div>
      <div className="grid gap-3">
        {data.map((c) => (
          <ClipCard
            key={c.filename}
            clip={c}
            progress={progress[c.filename]}
          />
        ))}
      </div>
    </div>
  );
}
