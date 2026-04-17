"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { SearchBar } from "./search-bar";
import { ResultCard } from "./result-card";
import { IndexPrompt } from "./index-prompt";

export function SearchPanel({ projectId }: { projectId: string }) {
  const [query, setQuery] = useState<string | null>(null);

  const indexStatus = useQuery({
    queryKey: [...queryKeys.project(projectId), "search-index"],
    queryFn: () => api.getIndexStatus(projectId),
    retry: false,
    refetchInterval: (q) => (q.state.data?.ready ? false : 3000),
  });

  const results = useQuery({
    queryKey: [...queryKeys.project(projectId), "search", query],
    queryFn: () => api.searchClips(projectId, query!),
    enabled: !!query && !!indexStatus.data?.ready,
  });

  if (
    indexStatus.error instanceof ApiError &&
    indexStatus.error.code === "search_extras_not_installed"
  ) {
    return <IndexPrompt projectId={projectId} reason="missing_deps" />;
  }

  if (!indexStatus.data || indexStatus.data.total === 0) {
    return <IndexPrompt projectId={projectId} reason="empty_index" />;
  }

  return (
    <div className="space-y-4">
      <SearchBar onSubmit={setQuery} />
      {!indexStatus.data.ready ? (
        <p className="text-sm text-[var(--color-muted)]">
          Indexing… {indexStatus.data.indexed}/{indexStatus.data.total} clips
          ({Math.round(
            (indexStatus.data.indexed / indexStatus.data.total) * 100,
          )}
          %)
        </p>
      ) : null}
      {results.isLoading ? (
        <p className="text-sm text-[var(--color-muted)]">Searching…</p>
      ) : null}
      {results.data ? (
        <div>
          <p className="text-sm text-[var(--color-muted)] mb-2">
            {results.data.hits.length} result
            {results.data.hits.length === 1 ? "" : "s"} for &ldquo;
            {results.data.query}&rdquo;
          </p>
          <div className="grid grid-cols-2 gap-3">
            {results.data.hits.map((h, i) => (
              <ResultCard key={i} hit={h} />
            ))}
          </div>
          {results.data.hits.length === 0 ? (
            <p className="text-sm text-[var(--color-placeholder)] py-8 text-center">
              No matches. Try different keywords.
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
