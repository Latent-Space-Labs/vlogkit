"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, type ExportFormat } from "@/lib/api";

const FORMATS: {
  value: ExportFormat;
  label: string;
  ext: string;
  desc: string;
}[] = [
  {
    value: "fcpxml",
    label: "Final Cut Pro XML",
    ext: "fcpxml",
    desc: "Final Cut / DaVinci Resolve",
  },
  { value: "edl", label: "EDL", ext: "edl", desc: "Classic edit decision list" },
  { value: "premiere", label: "Premiere XML", ext: "xml", desc: "Premiere Pro" },
  {
    value: "otio",
    label: "OpenTimelineIO",
    ext: "otio",
    desc: "OTIO reference format",
  },
];

export function ExportDialog({
  projectId,
  projectName,
  onClose,
}: {
  projectId: string;
  projectName: string;
  onClose: () => void;
}) {
  const [format, setFormat] = useState<ExportFormat>("fcpxml");
  const [status, setStatus] = useState<
    | { kind: "idle" }
    | { kind: "running" }
    | { kind: "done"; path: string }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  const mutation = useMutation({
    mutationFn: async () => {
      const spec = FORMATS.find((f) => f.value === format)!;
      const pickSave = (window as typeof window & {
        vlogkitSaveFile?: (opts: {
          defaultName: string;
          filters?: { name: string; extensions: string[] }[];
        }) => Promise<string | null>;
      }).vlogkitSaveFile;
      const destination = pickSave
        ? await pickSave({
            defaultName: `${projectName}.${spec.ext}`,
            filters: [{ name: spec.label, extensions: [spec.ext] }],
          })
        : prompt(`Save path (${spec.ext}):`, `${projectName}.${spec.ext}`);
      if (!destination) return null;
      setStatus({ kind: "running" });
      const res = await api.exportStoryboard(projectId, {
        format,
        destination,
      });
      return res;
    },
    onSuccess: (res) => {
      if (res) setStatus({ kind: "done", path: res.path });
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
        <h3 className="text-lg font-bold mb-4">Export storyboard</h3>
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
                name="format"
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
            ✓ Exported to {status.path}
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
              ? "Exporting…"
              : "Export"}
          </button>
        </div>
      </div>
    </div>
  );
}
