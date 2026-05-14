"use client";

import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function RegenerateButton({
  projectId,
  inFlight,
  onJobStarted,
}: {
  projectId: string;
  inFlight: boolean;
  onJobStarted?: (jobId: string) => void;
}) {
  const mut = useMutation({
    mutationFn: () => api.regenerateStoryboard(projectId),
    onSuccess: (resp) => onJobStarted?.(resp.job_id),
  });
  const running = mut.isPending || inFlight;
  return (
    <button
      onClick={() => mut.mutate()}
      disabled={running}
      className="px-3 py-1.5 rounded-[4px] font-semibold text-sm text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60 transition"
    >
      {running ? "Regenerating…" : "Regenerate"}
    </button>
  );
}
