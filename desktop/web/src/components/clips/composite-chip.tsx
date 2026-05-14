"use client";

/**
 * Color-tiered composite score chip.
 *
 * Tiers (numeric thresholds, tunable):
 *   0-49  → red bg, dark red text     (weak)
 *   50-69 → amber bg, dark amber text (mid)
 *   70-84 → emerald bg, dark emerald  (good)
 *   85-100→ gold bg, dark gold + ★    (excellent)
 *
 * If `mixed` (only some scenes scored), append a "(scored/total)" suffix.
 */
export function CompositeChip({
  score,
  scoredCount,
  totalCount,
}: {
  score: number;
  scoredCount?: number;
  totalCount?: number;
}) {
  const tier = tierFor(score);
  const showStar = tier === "excellent";
  const suffix =
    scoredCount !== undefined &&
    totalCount !== undefined &&
    scoredCount < totalCount
      ? ` (${scoredCount}/${totalCount})`
      : "";

  return (
    <span
      className={`text-xs font-semibold px-2 py-0.5 rounded-full ${classesFor(tier)}`}
      title={`Composite score ${score.toFixed(0)}${suffix}`}
    >
      {showStar ? "★ " : ""}
      {Math.round(score)}
      {suffix}
    </span>
  );
}

type Tier = "weak" | "mid" | "good" | "excellent";

function tierFor(score: number): Tier {
  if (score >= 85) return "excellent";
  if (score >= 70) return "good";
  if (score >= 50) return "mid";
  return "weak";
}

function classesFor(tier: Tier): string {
  switch (tier) {
    case "excellent": return "bg-yellow-100 text-yellow-900";
    case "good":      return "bg-emerald-100 text-emerald-900";
    case "mid":       return "bg-amber-100 text-amber-900";
    case "weak":      return "bg-red-100 text-red-900";
  }
}
