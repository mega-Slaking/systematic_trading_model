/**
 * ChartHeader: a caption shown above a chart, replacing the rotated y-axis title.
 * Themed (var tokens) and centred so it reads as the chart's header whether or
 * not a section/card title already sits above it. For dual-axis charts the
 * primary and secondary labels are joined (e.g. "NAV ($) · Sharpe").
 */

import type { ReactNode } from "react";

export function ChartHeader({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        fontFamily: "var(--font-dashboard)",
        fontSize: "0.85rem",
        fontWeight: 600,
        color: "var(--text-muted)",
        textAlign: "center",
        marginBottom: "0.35rem",
      }}
    >
      {children}
    </div>
  );
}
