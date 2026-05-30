"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, type TightenResponse } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

export function TightenButton({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const [preview, setPreview] = useState<TightenResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const dryRun = useMutation({
    mutationFn: () => api.tighten(projectId, true),
    onSuccess: (res) => {
      setError(null);
      setPreview(res);
    },
    onError: (err) => setError(String(err)),
  });

  const apply = useMutation({
    mutationFn: () => api.tighten(projectId, false),
    onSuccess: () => {
      setPreview(null);
      setError(null);
      qc.invalidateQueries({
        queryKey: [...queryKeys.project(projectId), "storyboard"],
      });
    },
    onError: (err) => setError(String(err)),
  });

  const running = dryRun.isPending || apply.isPending;

  return (
    <div className="relative">
      <button
        onClick={() => dryRun.mutate()}
        disabled={running}
        className="px-3 py-1.5 rounded-[4px] font-semibold text-sm text-[var(--color-foreground)] border border-[var(--color-border-whisper)] bg-white hover:border-[var(--color-muted)] disabled:opacity-60 transition"
      >
        {dryRun.isPending ? "Analyzing…" : "Tighten"}
      </button>
      {error && !preview ? (
        <div
          className="absolute right-0 top-full mt-2 z-20 w-[300px] bg-white rounded-[8px] p-3 border border-[var(--color-border-whisper)]"
          style={{ boxShadow: "var(--shadow-deep)" }}
        >
          <p className="text-sm text-red-600 mb-2">Error: {error}</p>
          <div className="flex justify-end">
            <button
              onClick={() => setError(null)}
              className="px-2 py-1 rounded-[4px] text-sm text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
            >
              Dismiss
            </button>
          </div>
        </div>
      ) : null}
      {preview ? (
        <div
          className="absolute right-0 top-full mt-2 z-20 w-[300px] bg-white rounded-[8px] p-3 border border-[var(--color-border-whisper)]"
          style={{ boxShadow: "var(--shadow-deep)" }}
        >
          {(() => {
            const pct =
              preview.original_duration > 0
                ? (preview.removed_duration / preview.original_duration) * 100
                : 0;
            return (
              <p className="text-sm mb-3">
                −{preview.removed_duration.toFixed(1)}s ({pct.toFixed(0)}%),{" "}
                {preview.segments_before}→{preview.segments_after} segments
              </p>
            );
          })()}
          {error ? (
            <p className="text-sm text-red-600 mb-2">Error: {error}</p>
          ) : null}
          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setPreview(null);
                setError(null);
              }}
              disabled={apply.isPending}
              className="px-2 py-1 rounded-[4px] text-sm text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
            >
              Cancel
            </button>
            <button
              onClick={() => apply.mutate()}
              disabled={apply.isPending}
              className="px-3 py-1 rounded-[4px] font-semibold text-sm text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60"
            >
              {apply.isPending ? "Applying…" : "Apply"}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
