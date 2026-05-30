"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type CaptionFormat } from "@/lib/api";

const FORMATS: {
  value: CaptionFormat;
  label: string;
  ext: string;
  desc: string;
}[] = [
  { value: "srt", label: "SubRip", ext: "srt", desc: "Widely supported (.srt)" },
  { value: "vtt", label: "WebVTT", ext: "vtt", desc: "Web video captions (.vtt)" },
  { value: "ass", label: "Advanced SubStation", ext: "ass", desc: "Styled subtitles (.ass)" },
];

export function CaptionsDialog({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const [format, setFormat] = useState<CaptionFormat>("srt");
  const [status, setStatus] = useState<
    | { kind: "idle" }
    | { kind: "running" }
    | { kind: "done"; path: string; cueCount: number }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  const mutation = useMutation({
    mutationFn: async () => {
      setStatus({ kind: "running" });
      return api.generateCaptions(projectId, format);
    },
    onSuccess: (res) => {
      setStatus({ kind: "done", path: res.path, cueCount: res.cue_count });
    },
    onError: (err) => {
      setStatus({ kind: "error", message: String(err) });
    },
  });

  return (
    <div
      className="fixed inset-0 z-20 flex items-center justify-center bg-black/20"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-[16px] p-6 w-[480px] max-w-full"
        style={{ boxShadow: "var(--shadow-deep)" }}
      >
        <h3 className="text-lg font-bold mb-4">Generate captions</h3>
        <div className="space-y-2 mb-4">
          {FORMATS.map((f) => (
            <label
              key={f.value}
              className={
                "flex items-start gap-3 p-3 rounded-[8px] border cursor-pointer transition " +
                (format === f.value
                  ? "border-[var(--color-accent)] bg-[var(--color-badge-bg)]"
                  : "border-[var(--color-border-whisper)] hover:border-[var(--color-muted)]")
              }
            >
              <input
                type="radio"
                name="caption-format"
                value={f.value}
                checked={format === f.value}
                onChange={() => setFormat(f.value)}
                className="mt-1"
              />
              <div>
                <div className="font-semibold text-sm">{f.label}</div>
                <div className="text-xs text-[var(--color-muted)]">
                  .{f.ext} · {f.desc}
                </div>
              </div>
            </label>
          ))}
        </div>
        {status.kind === "done" ? (
          <p className="text-sm text-green-700 mb-4 break-all">
            ✓ Wrote {status.cueCount} cues to {status.path}
          </p>
        ) : status.kind === "error" ? (
          <p className="text-sm text-red-600 mb-4">Error: {status.message}</p>
        ) : null}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-[4px] text-sm text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
          >
            Close
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || status.kind === "running"}
            className="px-4 py-1.5 rounded-[4px] font-semibold text-sm text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-strong)] disabled:opacity-60"
          >
            {mutation.isPending || status.kind === "running"
              ? "Generating…"
              : "Generate"}
          </button>
        </div>
      </div>
    </div>
  );
}
