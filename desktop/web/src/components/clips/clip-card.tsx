"use client";

import { useState } from "react";
import type { ClipSummary } from "@/lib/api";
import type { AnalyzeProgress } from "@/lib/events";
import { CompositeChip } from "./composite-chip";
import { SceneRow } from "./scene-row";

export function ClipCard({
  clip,
  progress,
}: {
  clip: ClipSummary;
  progress?: AnalyzeProgress;
}) {
  const analyzed = clip.status === "analyzed";
  const scenes = clip.analysis?.scenes ?? [];
  const scoredScenes = scenes.filter((s) => s.murch !== null);
  const hasAnyScores = scoredScenes.length > 0;
  const avgComposite =
    hasAnyScores
      ? scoredScenes.reduce((sum, s) => sum + (s.murch?.composite ?? 0), 0) /
        scoredScenes.length
      : 0;
  const canExpand = scenes.length > 0;

  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="bg-white rounded-[12px] border border-[var(--color-border-whisper)] p-4"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div
        className={canExpand ? "flex items-center justify-between cursor-pointer" : "flex items-center justify-between"}
        onClick={canExpand ? () => setExpanded((x) => !x) : undefined}
      >
        <div className="flex items-center gap-2">
          {canExpand && (
            <span className="text-[var(--color-muted)] text-sm w-3">
              {expanded ? "▾" : "▸"}
            </span>
          )}
          <div className="font-semibold">{clip.filename}</div>
        </div>
        <div className="flex items-center gap-2">
          {hasAnyScores && (
            <CompositeChip
              score={avgComposite}
              scoredCount={scoredScenes.length}
              totalCount={scenes.length}
            />
          )}
          <StatusPill status={clip.status} />
        </div>
      </div>
      <div className="text-xs text-[var(--color-placeholder)] mt-1">
        {(clip.size / 1024 / 1024).toFixed(1)} MB
        {scenes.length > 0 && ` · ${scenes.length} scene${scenes.length === 1 ? "" : "s"}`}
      </div>

      {!analyzed && progress && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-xs text-[var(--color-muted)]">
            <span>{progress.stage}</span>
            <span>{Math.round(progress.pct * 100)}%</span>
          </div>
          <div className="h-1 bg-[var(--color-background-alt)] rounded-full mt-1 overflow-hidden">
            <div
              className="h-full bg-[var(--color-accent)] transition-[width]"
              style={{ width: `${progress.pct * 100}%` }}
            />
          </div>
        </div>
      )}

      {canExpand && expanded && (
        <div className="mt-3 border-t border-[var(--color-border-whisper)] pt-2">
          {scenes.length === 0 ? (
            <p className="text-xs text-[var(--color-placeholder)] italic">
              No scenes detected.
            </p>
          ) : !hasAnyScores ? (
            <p className="text-xs text-[var(--color-placeholder)] italic">
              No scores yet. Run &quot;Score scenes&quot; to grade.
            </p>
          ) : (
            <div className="grid gap-1">
              {scenes.map((s, i) => (
                <SceneRow key={i} scene={s} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatusPill({ status }: { status: ClipSummary["status"] }) {
  const styles = {
    unanalyzed: "bg-[var(--color-background-alt)] text-[var(--color-muted)]",
    analyzed: "bg-[var(--color-badge-bg)] text-[var(--color-badge-text)]",
    failed: "bg-red-50 text-red-700",
  }[status];
  return (
    <span
      className={`text-xs font-semibold px-2 py-0.5 rounded-full ${styles}`}
    >
      {status}
    </span>
  );
}
