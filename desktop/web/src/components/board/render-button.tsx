"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type RenderResolution } from "@/lib/api";

export type RenderState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; outputPath: string }
  | { status: "failed"; error: string };

const RESOLUTIONS: { value: RenderResolution; label: string }[] = [
  { value: null, label: "Auto" },
  { value: "1080p", label: "1080p" },
  { value: "720p", label: "720p" },
];

export function RenderButton({
  projectId,
  state,
  onJobStarted,
  disabled = false,
}: {
  projectId: string;
  state: RenderState;
  onJobStarted: (jobId: string) => void;
  disabled?: boolean;
}) {
  const [captions, setCaptions] = useState(false);
  const [resolution, setResolution] = useState<RenderResolution>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.startRender(projectId, { captions, resolution, fps: null }),
    onSuccess: (resp) => onJobStarted(resp.job_id),
  });

  const running = mutation.isPending || state.status === "running";

  const label = (() => {
    if (mutation.isPending) return "Starting…";
    if (state.status === "running") return "Rendering…";
    if (state.status === "done") return "Render";
    if (state.status === "failed") return "Render (retry)";
    return "Render";
  })();

  return (
    <div className="flex items-center gap-2">
      <label className="flex items-center gap-1.5 text-sm text-[var(--color-muted)] cursor-pointer">
        <input
          type="checkbox"
          checked={captions}
          onChange={(e) => setCaptions(e.target.checked)}
          disabled={running}
        />
        Captions
      </label>
      <select
        value={resolution ?? ""}
        onChange={(e) => setResolution(e.target.value === "" ? null : e.target.value)}
        disabled={running}
        className="px-2 py-1.5 rounded-[4px] text-sm text-[var(--color-foreground)] border border-[var(--color-border-whisper)] bg-white disabled:opacity-60"
      >
        {RESOLUTIONS.map((r) => (
          <option key={r.label} value={r.value ?? ""}>
            {r.label}
          </option>
        ))}
      </select>
      <button
        onClick={() => mutation.mutate()}
        disabled={disabled || running}
        className="px-3 py-1.5 rounded-[4px] font-semibold text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60 text-sm transition"
        title={
          state.status === "failed"
            ? state.error
            : state.status === "done"
              ? `Rendered to ${state.outputPath}`
              : undefined
        }
      >
        {label}
      </button>
    </div>
  );
}
