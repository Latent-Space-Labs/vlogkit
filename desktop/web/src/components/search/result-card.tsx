import type { SearchHit } from "@/lib/api";
import { InsertIntoSection } from "./insert-into-section";

export function ResultCard({
  projectId,
  hit,
}: {
  projectId: string;
  hit: SearchHit;
}) {
  return (
    <div
      className="bg-white rounded-[8px] border border-[var(--color-border-whisper)] p-3"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="font-semibold text-sm truncate">
          {hit.clip_filename}
        </div>
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-[var(--color-badge-bg)] text-[var(--color-badge-text)]">
          {Math.round(hit.score * 100)}%
        </span>
      </div>
      <div className="text-xs text-[var(--color-placeholder)] mt-1">
        {hit.chunk_start.toFixed(1)}s → {hit.chunk_end.toFixed(1)}s
      </div>
      {hit.snippet ? (
        <p className="text-xs text-[var(--color-muted)] mt-2 line-clamp-3">
          {hit.snippet}
        </p>
      ) : null}
      <div className="mt-3 flex justify-end">
        <InsertIntoSection projectId={projectId} hit={hit} />
      </div>
    </div>
  );
}
