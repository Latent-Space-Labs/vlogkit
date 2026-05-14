"use client";

import { useEffect, useState } from "react";
import type { Storyboard, StoryboardSegment } from "@/lib/api";
import type { components } from "@/lib/api-types";
import { CompositeChip } from "@/components/clips/composite-chip";
import { DimensionBar } from "@/components/clips/dimension-bar";
import { SceneTypeChip } from "@/components/clips/scene-type-chip";
import { ClipPreview } from "./clip-preview";

type ClipScene = components["schemas"]["ClipScene"];

function findSceneAtTime(scenes: ClipScene[], time: number): ClipScene | null {
  for (const s of scenes) {
    if (time >= s.start && time < s.end) return s;
  }
  return null;
}

export function InspectorDrawer({
  segment,
  sectionIndex,
  segmentIndex,
  storyboard,
  clipSha256,
  clipScenes,
  onSave,
}: {
  segment: StoryboardSegment;
  sectionIndex: number;
  segmentIndex: number;
  storyboard: Storyboard;
  clipSha256: string | null | undefined;
  clipScenes?: ClipScene[];
  onSave: (next: Storyboard) => void;
}) {
  const [label, setLabel] = useState(segment.label ?? "");
  const [inPoint, setInPoint] = useState(segment.in_point);
  const [outPoint, setOutPoint] = useState(segment.out_point);

  // Reset form whenever the selected segment changes.
  useEffect(() => {
    setLabel(segment.label ?? "");
    setInPoint(segment.in_point);
    setOutPoint(segment.out_point);
  }, [segment]);

  // Debounced save.
  useEffect(() => {
    const handle = setTimeout(() => {
      if (
        label === (segment.label ?? "") &&
        inPoint === segment.in_point &&
        outPoint === segment.out_point
      ) {
        return;
      }
      const next: Storyboard = JSON.parse(JSON.stringify(storyboard));
      const sections = next.sections ?? [];
      const sec = sections[sectionIndex];
      if (!sec || !sec.segments) return;
      sec.segments[segmentIndex] = {
        ...segment,
        label,
        in_point: inPoint,
        out_point: outPoint,
      };
      onSave(next);
    }, 500);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [label, inPoint, outPoint]);

  const duration = Math.max(0, outPoint - inPoint);

  // Murch readout — find the scene that brackets the segment's in_point
  const scene = clipScenes ? findSceneAtTime(clipScenes, segment.in_point) : null;

  return (
    <div className="space-y-4">
      {clipScenes && (
        scene === null ? null : !scene.murch ? (
          <p className="text-xs text-[var(--color-placeholder)] italic">
            This scene hasn&apos;t been scored yet. Run &quot;Score scenes&quot; on the clips tab.
          </p>
        ) : (
          <div className="p-3 bg-[var(--color-background-alt)] rounded-md">
            <div className="flex items-center gap-2 mb-2">
              <SceneTypeChip type={scene.murch.scene_type} />
              <CompositeChip score={scene.murch.composite} />
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <DimRow label="Aesthetic" value={scene.murch.aesthetic} />
              <DimRow label="Credibility" value={scene.murch.credibility} />
              <DimRow label="Impact" value={scene.murch.impact} />
              <DimRow label="Memorability" value={scene.murch.memorability} />
              <DimRow label="Fun" value={scene.murch.fun} />
            </div>
            {scene.murch.rationale && (
              <p className="text-xs text-[var(--color-muted)] italic mt-2">
                &quot;{scene.murch.rationale}&quot;
              </p>
            )}
          </div>
        )
      )}
      <ClipPreview clipSha256={clipSha256} start={inPoint} end={outPoint} />
      <label className="block">
        <span className="text-xs text-[var(--color-muted)]">Label</span>
        <input
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Untitled segment"
          className="mt-1 w-full rounded-[4px] border border-[var(--color-border-whisper)] bg-white px-2 py-1 text-sm"
        />
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="text-xs text-[var(--color-muted)]">In (s)</span>
          <input
            type="number"
            step="0.1"
            min="0"
            value={inPoint}
            onChange={(e) => setInPoint(parseFloat(e.target.value) || 0)}
            className="mt-1 w-full rounded-[4px] border border-[var(--color-border-whisper)] bg-white px-2 py-1 text-sm"
          />
        </label>
        <label className="block">
          <span className="text-xs text-[var(--color-muted)]">Out (s)</span>
          <input
            type="number"
            step="0.1"
            min="0"
            value={outPoint}
            onChange={(e) => setOutPoint(parseFloat(e.target.value) || 0)}
            className="mt-1 w-full rounded-[4px] border border-[var(--color-border-whisper)] bg-white px-2 py-1 text-sm"
          />
        </label>
      </div>
      <p className="text-xs text-[var(--color-placeholder)]">
        Duration: {duration.toFixed(1)}s · {segment.clip_path}
      </p>
    </div>
  );
}

function DimRow({ label, value }: { label: string; value: number }) {
  return (
    <span className="flex items-center gap-2">
      <span className="text-[var(--color-muted)] w-20">{label}</span>
      <DimensionBar value={value} width={48} />
      <span className="font-semibold">{Math.round(value)}</span>
    </span>
  );
}
