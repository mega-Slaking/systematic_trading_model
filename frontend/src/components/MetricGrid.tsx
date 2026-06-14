/**
 * MetricGrid (spec §7.2): the tearsheet metric tiles -- the `st.metric` equivalent.
 * A responsive grid of label/value cards; each value is formatted client-side per
 * its `format` (the API returns raw numbers, §4.1). `null` renders as an em dash.
 */

import type { ReactNode } from "react";

import { formatCurrency, formatPercent, formatRatio } from "../lib/format";

export type MetricFormat = "percent" | "ratio" | "currency" | "number";

export interface Metric {
  label: string;
  value: number | string | null;
  format: MetricFormat;
}

function formatMetric(metric: Metric): ReactNode {
  if (typeof metric.value === "string") return metric.value;
  switch (metric.format) {
    case "percent":
      return formatPercent(metric.value);
    case "currency":
      return formatCurrency(metric.value);
    case "ratio":
    case "number":
      return formatRatio(metric.value);
  }
}

export function MetricGrid({ metrics }: { metrics: Metric[] }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))",
        gap: "0.6rem",
      }}
    >
      {metrics.map((metric) => (
        <div
          key={metric.label}
          style={{ border: "1px solid var(--border-soft)", borderRadius: 8, padding: "0.6rem 0.75rem", background: "var(--surface-raised)" }}
        >
          <div style={{ fontSize: "0.72rem", color: "var(--text-subtle)", textTransform: "uppercase", letterSpacing: "0.02em" }}>
            {metric.label}
          </div>
          <div
            style={{
              fontSize: "1.15rem",
              fontWeight: 400,
              marginTop: "0.2rem",
              fontVariantNumeric: "tabular-nums",
              fontFamily: "var(--font-data)", // Play (regular weight) for the numeric value
            }}
          >
            {formatMetric(metric)}
          </div>
        </div>
      ))}
    </div>
  );
}
