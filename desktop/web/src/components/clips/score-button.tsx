"use client";

import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

export type ScoreState =
  | { status: "idle" }
  | { status: "running"; scored: number; total: number }
  | { status: "completed" }
  | { status: "failed"; error: string };

export function ScoreButton({
  projectId,
  state,
  onJobStarted,
  disabled = false,
}: {
  projectId: string;
  state: ScoreState;
  onJobStarted: (jobId: string) => void;
  disabled?: boolean;
}) {
  const mutation = useMutation({
    mutationFn: () => api.score(projectId),
    onSuccess: (resp) => onJobStarted(resp.job_id),
  });

  const label = (() => {
    if (mutation.isPending) return "Starting…";
    if (state.status === "running") {
      return `Scoring ${state.scored} of ${state.total}…`;
    }
    if (state.status === "completed") return "Scored";
    if (state.status === "failed") return "Score failed (retry)";
    return "Score scenes";
  })();

  return (
    <button
      onClick={() => mutation.mutate()}
      disabled={disabled || mutation.isPending || state.status === "running"}
      className="px-3 py-1.5 rounded-[4px] font-semibold text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60 text-sm transition"
      title={state.status === "failed" ? state.error : undefined}
    >
      {label}
    </button>
  );
}
