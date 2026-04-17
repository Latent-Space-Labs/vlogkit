"use client";

import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function AnalyzeButton({ projectId }: { projectId: string }) {
  const mutation = useMutation({
    mutationFn: () => api.startAnalyze(projectId),
  });
  return (
    <button
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending}
      className="px-3 py-1.5 rounded-[4px] font-semibold text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60 text-sm transition"
    >
      {mutation.isPending ? "Starting…" : "Analyze"}
    </button>
  );
}
