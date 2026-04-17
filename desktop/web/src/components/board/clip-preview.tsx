"use client";

import { useEffect, useRef } from "react";
import { getMediaUrl } from "@/lib/api";

export function ClipPreview({
  clipSha256,
  start,
  end,
}: {
  clipSha256: string | null | undefined;
  start: number;
  end: number;
}) {
  const ref = useRef<HTMLVideoElement>(null);

  // Seek to start whenever the segment (or clip) changes.
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    const onLoaded = () => {
      v.currentTime = start;
    };
    v.addEventListener("loadedmetadata", onLoaded);
    // If metadata is already loaded, seek now.
    if (v.readyState >= 1) v.currentTime = start;
    return () => v.removeEventListener("loadedmetadata", onLoaded);
  }, [start, clipSha256]);

  if (!clipSha256) {
    return (
      <div className="aspect-video bg-[var(--color-background-alt)] rounded-[8px] flex items-center justify-center text-sm text-[var(--color-muted)] text-center px-4">
        Clip not analyzed yet — no preview available
      </div>
    );
  }

  return (
    <video
      ref={ref}
      src={getMediaUrl(clipSha256)}
      controls
      className="w-full rounded-[8px] border border-[var(--color-border-whisper)] bg-black"
      onTimeUpdate={(e) => {
        const v = e.currentTarget;
        if (v.currentTime > end) v.pause();
      }}
    />
  );
}
