"use client";

import { useEffect, useState } from "react";
import type { Storyboard, StoryboardSegment } from "@/lib/api";
import { ClipPreview } from "./clip-preview";

export function InspectorDrawer({
  segment,
  sectionIndex,
  segmentIndex,
  storyboard,
  clipSha256,
  onSave,
}: {
  segment: StoryboardSegment;
  sectionIndex: number;
  segmentIndex: number;
  storyboard: Storyboard;
  clipSha256: string | null | undefined;
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
      // Deep clone and mutate the target segment only.
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

  return (
    <div className="space-y-4">
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
