"use client";

import type { components } from "@/lib/api-types";

type SceneType = components["schemas"]["ClipMurchScore"]["scene_type"];

const STYLES: Record<SceneType, string> = {
  hook:       "bg-blue-100 text-blue-900",
  narrative:  "bg-amber-100 text-amber-900",
  aesthetic:  "bg-emerald-100 text-emerald-900",
  commercial: "bg-purple-100 text-purple-900",
};

export function SceneTypeChip({ type }: { type: SceneType }) {
  return (
    <span
      className={`text-[10px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded ${STYLES[type]}`}
    >
      {type}
    </span>
  );
}
