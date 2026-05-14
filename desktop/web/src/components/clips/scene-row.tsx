"use client";

import type { components } from "@/lib/api-types";
import { CompositeChip } from "./composite-chip";
import { DimensionBar } from "./dimension-bar";
import { SceneTypeChip } from "./scene-type-chip";

type ClipScene = components["schemas"]["ClipScene"];

function formatTime(s: number): string {
  if (s < 60) return `${s.toFixed(0)}s`;
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export function SceneRow({ scene }: { scene: ClipScene }) {
  if (!scene.murch) {
    return (
      <div className="grid grid-cols-[60px_1fr] gap-2 py-1 text-xs text-[var(--color-placeholder)]">
        <span>{formatTime(scene.start)}–{formatTime(scene.end)}</span>
        <span className="italic">unscored</span>
      </div>
    );
  }
  const m = scene.murch;
  return (
    <div className="grid grid-cols-[60px_80px_50px_1fr] gap-2 py-1 items-center text-xs">
      <span className="text-[var(--color-muted)]">
        {formatTime(scene.start)}–{formatTime(scene.end)}
      </span>
      <span><SceneTypeChip type={m.scene_type} /></span>
      <span><CompositeChip score={m.composite} /></span>
      <span className="flex items-center gap-1">
        <DimensionBar value={m.aesthetic} label="Aesthetic" />
        <DimensionBar value={m.credibility} label="Credibility" />
        <DimensionBar value={m.impact} label="Impact" />
        <DimensionBar value={m.memorability} label="Memorability" />
        <DimensionBar value={m.fun} label="Fun" />
      </span>
    </div>
  );
}
