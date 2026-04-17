"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type StoryboardSegment } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { SectionRow } from "./section-row";
import { EmptyBoard } from "./empty-board";

export function Board({ projectId }: { projectId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: [...queryKeys.project(projectId), "storyboard"],
    queryFn: () => api.getStoryboard(projectId),
    retry: false,
  });
  const [selected, setSelected] = useState<{
    key: string;
    segment: StoryboardSegment;
  } | null>(null);

  if (isLoading) {
    return <p className="text-[var(--color-muted)]">Loading storyboard…</p>;
  }
  // 404 with code "storyboard_not_found" means no storyboard yet — show empty state.
  if (error instanceof ApiError && error.code === "storyboard_not_found") {
    return <EmptyBoard projectId={projectId} />;
  }
  if (error) {
    return <p className="text-red-600">Error: {String(error)}</p>;
  }
  if (!data) return <EmptyBoard projectId={projectId} />;

  return (
    <div className="grid grid-cols-[1fr_320px] gap-6">
      <div>
        <div className="mb-4">
          <h2 className="text-2xl font-bold">{data.title}</h2>
          {data.llm_rationale ? (
            <p className="text-sm text-[var(--color-muted)] mt-1">
              {data.llm_rationale}
            </p>
          ) : null}
        </div>
        {(data.sections ?? []).map((s, i) => (
          <SectionRow
            key={i}
            section={s}
            selectedSegmentKey={selected?.key ?? null}
            onSelectSegment={(key, segment) => setSelected({ key, segment })}
          />
        ))}
      </div>
      <aside className="bg-[var(--color-background-alt)] rounded-[12px] p-4 h-fit sticky top-6">
        {selected ? (
          <>
            <h4 className="font-semibold mb-2">
              {selected.segment.label || "Untitled segment"}
            </h4>
            <p className="text-sm text-[var(--color-muted)] break-all">
              {selected.segment.clip_path}
            </p>
            <p className="text-xs text-[var(--color-placeholder)] mt-2">
              Preview + editing coming in Tasks 5 and 6.
            </p>
          </>
        ) : (
          <p className="text-sm text-[var(--color-muted)]">
            Select a segment to inspect it.
          </p>
        )}
      </aside>
    </div>
  );
}
