"use client";

/**
 * Small inline horizontal bar (0-100 → width). Used for the per-scene
 * dimension visualization in scene rows and the inspector readout.
 */
export function DimensionBar({
  value,
  label,
  width = 32,
}: {
  value: number;
  label?: string;
  width?: number;
}) {
  const pct = Math.max(0, Math.min(100, value));
  const barWidth = (pct / 100) * width;
  return (
    <span
      className="inline-flex items-center gap-1"
      title={label ? `${label}: ${value.toFixed(0)}` : `${value.toFixed(0)}`}
    >
      <span
        className="inline-block h-2 bg-gray-200 rounded-sm"
        style={{ width: `${width}px` }}
      >
        <span
          className="inline-block h-2 bg-blue-500 rounded-sm"
          style={{ width: `${barWidth}px` }}
        />
      </span>
    </span>
  );
}
