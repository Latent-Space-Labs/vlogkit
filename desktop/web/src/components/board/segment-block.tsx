import type { StoryboardSegment } from "@/lib/api";

// Derive just the filename from a full clip_path for display.
function basename(p: string): string {
  const i = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  return i >= 0 ? p.slice(i + 1) : p;
}

export function SegmentBlock({
  segment,
  selected,
  onSelect,
}: {
  segment: StoryboardSegment;
  selected: boolean;
  onSelect: () => void;
}) {
  const duration = segment.out_point - segment.in_point;
  return (
    <button
      onClick={onSelect}
      className={
        "text-left bg-white rounded-[8px] border p-3 min-w-[200px] transition " +
        (selected
          ? "border-[var(--color-accent)] ring-1 ring-[var(--color-accent-focus)]"
          : "border-[var(--color-border-whisper)] hover:border-[var(--color-muted)]")
      }
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="font-semibold text-sm truncate">
        {segment.label || "Untitled segment"}
      </div>
      <div className="text-xs text-[var(--color-muted)] truncate mt-1">
        {basename(segment.clip_path)}
      </div>
      <div className="text-xs text-[var(--color-placeholder)] mt-1">
        {segment.in_point.toFixed(1)}s → {segment.out_point.toFixed(1)}s
        ({duration.toFixed(1)}s)
      </div>
    </button>
  );
}
