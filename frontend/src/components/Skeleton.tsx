/**
 * Skeleton placeholders for loading states on the heavier pages — a calmer cue
 * than a bare "Loading…" string. Pure presentation; the pulse animation lives in
 * index.css (`.skeleton`).
 */

import type { CSSProperties } from "react";

export function Skeleton({
  height = 16,
  width = "100%",
  radius = 6,
  style,
}: {
  height?: number | string;
  width?: number | string;
  radius?: number;
  style?: CSSProperties;
}) {
  return <div className="skeleton" style={{ height, width, borderRadius: radius, ...style }} />;
}

/** Full-width placeholder sized like a chart. */
export function ChartSkeleton({ height = 400 }: { height?: number }) {
  return <Skeleton height={height} radius={8} style={{ marginTop: "0.25rem" }} />;
}

/** A few placeholder rows sized like a data table. */
export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} height={28} />
      ))}
    </div>
  );
}
