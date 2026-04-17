"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { arrayMove } from "@dnd-kit/sortable";

import { ApiError, api, type Storyboard, type StoryboardSegment } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { SectionRow } from "./section-row";
import { EmptyBoard } from "./empty-board";
import { useSegmentReorder } from "./use-segment-reorder";

export function Board({ projectId }: { projectId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: [...queryKeys.project(projectId), "storyboard"],
    queryFn: () => api.getStoryboard(projectId),
    retry: false,
  });
  const reorder = useSegmentReorder(projectId);
  const [selected, setSelected] = useState<{
    key: string;
    segment: StoryboardSegment;
  } | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  function handleDragEnd(evt: DragEndEvent) {
    const { active, over } = evt;
    if (!over || !data || active.id === over.id) return;
    const [fromSec, fromIdx] = String(active.id).split(":").map(Number);
    const [toSec, toIdx] = String(over.id).split(":").map(Number);
    if (fromSec !== toSec) return; // cross-section reorder deferred
    const next: Storyboard = JSON.parse(JSON.stringify(data));
    const sections = next.sections ?? [];
    const sec = sections[fromSec];
    if (!sec) return;
    sec.segments = arrayMove(sec.segments ?? [], fromIdx, toIdx);
    reorder.mutate(next);
  }

  if (isLoading) {
    return <p className="text-[var(--color-muted)]">Loading storyboard…</p>;
  }
  if (error instanceof ApiError && error.code === "storyboard_not_found") {
    return <EmptyBoard projectId={projectId} />;
  }
  if (error) {
    return <p className="text-red-600">Error: {String(error)}</p>;
  }
  if (!data) return <EmptyBoard projectId={projectId} />;

  const sections = data.sections ?? [];

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
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
          {sections.map((s, i) => (
            <SectionRow
              key={i}
              sectionIndex={i}
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
                Preview + editing coming in Task 6.
              </p>
            </>
          ) : (
            <p className="text-sm text-[var(--color-muted)]">
              Select a segment to inspect it.
            </p>
          )}
        </aside>
      </div>
    </DndContext>
  );
}
