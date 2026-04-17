import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { StoryboardSegment } from "@/lib/api";

function basename(p: string): string {
  const i = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  return i >= 0 ? p.slice(i + 1) : p;
}

export function SegmentBlock({
  id,
  segment,
  selected,
  onSelect,
}: {
  id: string;
  segment: StoryboardSegment;
  selected: boolean;
  onSelect: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    boxShadow: "var(--shadow-card)",
  };
  const duration = segment.out_point - segment.in_point;
  return (
    <button
      ref={setNodeRef}
      onClick={onSelect}
      {...attributes}
      {...listeners}
      style={style}
      className={
        "text-left bg-white rounded-[8px] border p-3 min-w-[200px] transition cursor-grab active:cursor-grabbing " +
        (selected
          ? "border-[var(--color-accent)] ring-1 ring-[var(--color-accent-focus)]"
          : "border-[var(--color-border-whisper)] hover:border-[var(--color-muted)]")
      }
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
