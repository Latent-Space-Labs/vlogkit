"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { connectEventStream } from "@/lib/ws";
import type { BoardEvent, AnalyzeProgress } from "@/lib/events";
import { ClipCard } from "./clip-card";
import { AnalyzeButton } from "./analyze-button";
import { ScoreButton, type ScoreState } from "./score-button";

export function ClipsTab({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.clips(projectId),
    queryFn: () => api.listClips(projectId),
  });
  const [progress, setProgress] = useState<Record<string, AnalyzeProgress>>({});
  const [scoreJobId, setScoreJobId] = useState<string | null>(null);
  const [scoreState, setScoreState] = useState<ScoreState>({ status: "idle" });

  useEffect(() => {
    const disconnect = connectEventStream(projectId, (evt: BoardEvent) => {
      // Existing analyze routing
      if (evt.type === "analyze.progress") {
        setProgress((p) => ({ ...p, [evt.clip_filename]: evt }));
      } else if (evt.type === "analyze.clip_done") {
        setProgress((p) => {
          const { [evt.clip_filename]: _, ...rest } = p;
          return rest;
        });
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      } else if (evt.type === "analyze.clip_failed") {
        setProgress((p) => {
          const { [evt.clip_filename]: _, ...rest } = p;
          return rest;
        });
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      } else if (evt.type === "analyze.complete") {
        setProgress({});
        qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
      }

      // New: score event routing — only act on events for the active score job
      if ("job_id" in evt && scoreJobId && evt.job_id === scoreJobId) {
        if (evt.type === "score.started") {
          setScoreState({ status: "running", scored: 0, total: evt.total_scenes });
        } else if (evt.type === "score.progress") {
          setScoreState({
            status: "running",
            scored: evt.scored,
            total: evt.total_scenes,
          });
        } else if (evt.type === "score.clip_done") {
          // Refetch clips so the per-clip composite chip updates live
          qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
        } else if (evt.type === "score.complete") {
          setScoreState({ status: "completed" });
          setScoreJobId(null);
          qc.invalidateQueries({ queryKey: queryKeys.clips(projectId) });
        } else if (evt.type === "score.failed") {
          setScoreState({ status: "failed", error: evt.error });
          setScoreJobId(null);
        }
      }
    });
    return disconnect;
  }, [projectId, qc, scoreJobId]);

  if (isLoading) return <p className="text-[var(--color-muted)]">Loading clips…</p>;
  if (error) return <p className="text-red-600">Error: {String(error)}</p>;
  if (!data || data.length === 0) {
    return (
      <p className="text-[var(--color-muted)] py-12 text-center">
        No clips in this folder.
      </p>
    );
  }

  // Score button is disabled until at least one clip is analyzed
  const anyAnalyzed = data.some((c) => c.status === "analyzed");

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-[var(--color-muted)]">{data.length} clips</p>
        <div className="flex items-center gap-2">
          <AnalyzeButton projectId={projectId} />
          <ScoreButton
            projectId={projectId}
            state={scoreState}
            disabled={!anyAnalyzed}
            onJobStarted={(jobId) => {
              setScoreJobId(jobId);
              setScoreState({ status: "running", scored: 0, total: 0 });
            }}
          />
        </div>
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
