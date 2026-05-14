"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
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
import { connectEventStream } from "@/lib/ws";
import { SectionRow } from "./section-row";
import { EmptyBoard } from "./empty-board";
import { useSegmentReorder } from "./use-segment-reorder";
import { InspectorDrawer } from "./inspector-drawer";
import { RegenerateButton } from "./regenerate-button";
import { ExportDialog } from "./export-dialog";
import {
  AgentProgressStepper,
  INITIAL_AGENT_STEPS,
  type AgentSteps,
} from "./agent-progress-stepper";

export function Board({ projectId }: { projectId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: [...queryKeys.project(projectId), "storyboard"],
    queryFn: () => api.getStoryboard(projectId),
    retry: false,
  });
  const reorder = useSegmentReorder(projectId);
  const { data: clips } = useQuery({
    queryKey: queryKeys.clips(projectId),
    queryFn: () => api.listClips(projectId),
  });

  function basename(p: string): string {
    const i = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
    return i >= 0 ? p.slice(i + 1) : p;
  }
  const hashMap = new Map<string, string>();
  (clips ?? []).forEach((c) => {
    if (c.sha256) hashMap.set(c.filename, c.sha256);
  });
  const [selected, setSelected] = useState<{
    key: string;
    segment: StoryboardSegment;
  } | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  const qc = useQueryClient();
  const [regenInFlight, setRegenInFlight] = useState(false);
  const [agentJobId, setAgentJobId] = useState<string | null>(null);
  const [agentSteps, setAgentSteps] = useState<AgentSteps>(INITIAL_AGENT_STEPS);
  const [showStepper, setShowStepper] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);

  useEffect(() => {
    const dc = connectEventStream(projectId, (evt) => {
      if (evt.type === "storyboard.regen_started") {
        setRegenInFlight(true);
      } else if (
        evt.type === "storyboard.regen_complete" ||
        evt.type === "storyboard.regen_failed"
      ) {
        setRegenInFlight(false);
        qc.invalidateQueries({
          queryKey: [...queryKeys.project(projectId), "storyboard"],
        });
      }

      // New: storyboard.agent_* event routing for the active regenerate job
      if ("job_id" in evt && agentJobId && evt.job_id === agentJobId) {
        if (evt.type === "storyboard.agent_started") {
          setShowStepper(true); // first agent event mounts the stepper
          setAgentSteps((prev) => ({
            ...prev,
            [evt.stage]: { status: "active", summary: "" },
          }));
        } else if (evt.type === "storyboard.agent_complete") {
          setAgentSteps((prev) => ({
            ...prev,
            [evt.stage]: { status: "done", summary: evt.summary },
          }));
        } else if (evt.type === "storyboard.agent_failed") {
          setAgentSteps((prev) => ({
            ...prev,
            [evt.stage]: { status: "failed", summary: evt.reason },
          }));
        }
      }
    });
    return dc;
  }, [projectId, qc, agentJobId]);

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
    <>
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="grid grid-cols-[1fr_320px] gap-6">
        <div>
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-2xl font-bold">{data.title}</h2>
              {data.llm_rationale ? (
                <p className="text-sm text-[var(--color-muted)] mt-1">
                  {data.llm_rationale}
                </p>
              ) : null}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setExportOpen(true)}
                className="px-3 py-1.5 rounded-[4px] font-semibold text-sm text-[var(--color-foreground)] border border-[var(--color-border-whisper)] bg-white hover:border-[var(--color-muted)]"
              >
                Export
              </button>
              <RegenerateButton
                projectId={projectId}
                inFlight={regenInFlight}
                onJobStarted={(jobId) => {
                  setAgentJobId(jobId);
                  setAgentSteps(INITIAL_AGENT_STEPS);
                  // Don't setShowStepper(true) here — only the first agent_started event mounts it.
                  // If chronological_fallback is used (no API key), no agent events fire and stepper stays unmounted.
                }}
              />
            </div>
          </div>
          {showStepper && (
            <div className="mb-4">
              <AgentProgressStepper
                steps={agentSteps}
                onComplete={() => {
                  setShowStepper(false);
                  setAgentJobId(null);
                  setAgentSteps(INITIAL_AGENT_STEPS);
                }}
              />
            </div>
          )}
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
          {selected && data ? (() => {
            const filename = basename(selected.segment.clip_path);
            const matchingClip = (clips ?? []).find((c) => c.filename === filename);
            return (
              <InspectorDrawer
                segment={selected.segment}
                sectionIndex={Number(selected.key.split(":")[0])}
                segmentIndex={Number(selected.key.split(":")[1])}
                storyboard={data}
                clipSha256={hashMap.get(filename)}
                clipScenes={matchingClip?.analysis?.scenes ?? undefined}
                onSave={(next) => reorder.mutate(next)}
              />
            );
          })() : (
            <p className="text-sm text-[var(--color-muted)]">
              Select a segment to inspect it.
            </p>
          )}
        </aside>
        </div>
      </DndContext>
      {exportOpen ? (
        <ExportDialog
          projectId={projectId}
          projectName={data.title || "storyboard"}
          onClose={() => setExportOpen(false)}
        />
      ) : null}
    </>
  );
}
