import type { ClipSummary } from "@/lib/api";
import type { AnalyzeProgress } from "@/lib/events";

export function ClipCard({
  clip,
  progress,
}: {
  clip: ClipSummary;
  progress?: AnalyzeProgress;
}) {
  const analyzed = clip.status === "analyzed";
  return (
    <div
      className="bg-white rounded-[12px] border border-[var(--color-border-whisper)] p-4"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="flex items-center justify-between">
        <div className="font-semibold">{clip.filename}</div>
        <StatusPill status={clip.status} />
      </div>
      <div className="text-xs text-[var(--color-placeholder)] mt-1">
        {(clip.size / 1024 / 1024).toFixed(1)} MB
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
