"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function IndexPrompt({
  projectId,
  reason,
}: {
  projectId: string;
  reason: "missing_deps" | "empty_index";
}) {
  const qc = useQueryClient();
  const mut = useMutation({
    mutationFn: () => api.buildSearchIndex(projectId),
    onSuccess: () => qc.invalidateQueries(),
  });

  if (reason === "missing_deps") {
    return (
      <div className="text-center py-16 px-8">
        <h2 className="text-xl font-bold mb-2">Search extras not installed</h2>
        <p className="text-[var(--color-muted)] max-w-md mx-auto text-sm mb-3">
          Install the optional dependencies to enable semantic search:
        </p>
        <code className="text-xs bg-[var(--color-background-alt)] rounded-[4px] px-3 py-2 inline-block">
          pip install -e &apos;.[search]&apos;
        </code>
      </div>
    );
  }

  return (
    <div className="text-center py-16 px-8">
      <h2 className="text-xl font-bold mb-2">No search index yet</h2>
      <p className="text-[var(--color-muted)] max-w-md mx-auto mb-5 text-sm">
        Build a search index of this project&apos;s analyzed clips so you can
        search by visual content (e.g. &quot;sunset over bridge&quot;).
      </p>
      <button
        onClick={() => mut.mutate()}
        disabled={mut.isPending}
        className="px-4 py-2 rounded-[4px] font-semibold text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60"
      >
        {mut.isPending ? "Starting index…" : "Build index"}
      </button>
    </div>
  );
}
