"use client";

import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, type Storyboard, type SearchHit } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";

export function InsertIntoSection({
  projectId,
  hit,
}: {
  projectId: string;
  hit: SearchHit;
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data: storyboard, error } = useQuery({
    queryKey: [...queryKeys.project(projectId), "storyboard"],
    queryFn: () => api.getStoryboard(projectId),
    retry: false,
  });

  const mutation = useMutation({
    mutationFn: (next: Storyboard) => api.putStoryboard(projectId, next),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: [...queryKeys.project(projectId), "storyboard"],
      });
      setOpen(false);
    },
  });

  if (error instanceof ApiError && error.code === "storyboard_not_found") {
    return (
      <span className="text-xs text-[var(--color-placeholder)]">
        Generate a storyboard first
      </span>
    );
  }
  if (!storyboard) return null;
  const sections = storyboard.sections ?? [];

  function insertInto(sectionIndex: number) {
    if (!storyboard) return;
    const next: Storyboard = JSON.parse(JSON.stringify(storyboard));
    const allSections = next.sections ?? [];
    const sec = allSections[sectionIndex];
    if (!sec) return;
    const segments = sec.segments ?? [];
    segments.push({
      clip_path: hit.clip_filename,
      in_point: hit.chunk_start,
      out_point: hit.chunk_end,
      label: "(from search)",
      transition: "",
      include: true,
    });
    sec.segments = segments;
    next.sections = allSections;
    mutation.mutate(next);
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="text-xs font-semibold text-[var(--color-accent)] hover:text-[var(--color-accent-strong)]"
      >
        + Insert into section
      </button>
      {open ? (
        <div
          className="absolute right-0 mt-1 bg-white border border-[var(--color-border-whisper)] rounded-[8px] z-10 min-w-[180px]"
          style={{ boxShadow: "var(--shadow-deep)" }}
        >
          {sections.map((s, i) => (
            <button
              key={i}
              onClick={() => insertInto(i)}
              disabled={mutation.isPending}
              className="block w-full text-left px-3 py-2 text-sm hover:bg-[var(--color-background-alt)] disabled:opacity-60"
            >
              {s.title}
            </button>
          ))}
          {sections.length === 0 ? (
            <p className="p-3 text-xs text-[var(--color-placeholder)]">
              No sections yet
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
