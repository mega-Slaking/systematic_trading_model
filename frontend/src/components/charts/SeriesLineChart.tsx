/**
 * SeriesLineChart (spec §7.2): renders `NamedSeries[]` as a Recharts multi-line
 * chart -- the shared line primitive for tabs 1, 3, 4, 5, 6 (the dense returns
 * scatter uses Plotly WebGL instead, §7.1).
 *
 * The per-series points are merged into one date-keyed dataset (Recharts' shape).
 * A `null` value (a NaN mapped to null at the API boundary, §6) renders as a line
 * gap via `connectNulls={false}` -- e.g. the trailing 2026-06-09 placeholder row.
 */

import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { NamedSeries } from "../../api/types";
import { useChartColors } from "../../theme/chartTheme";
import { theme } from "../../theme";
import { ChartHeader } from "./ChartHeader";

// Fallback palette for series whose name isn't a known ticker.
const PALETTE = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"];

function colorFor(name: string, index: number): string {
  const tickerColor = (theme.tickers as Record<string, string | undefined>)[name];
  return tickerColor ?? PALETTE[index % PALETTE.length];
}

interface SeriesLineChartProps {
  series: readonly NamedSeries[];
  yLabel?: string;
  height?: number;
  /** Formats Y-axis tick values (e.g. currency); defaults to the raw number. */
  valueFormatter?: (value: number) => string;
}

// `date` is a named string field; series values are added by ticker name. The
// index signature widens to include `string` so `date` is compatible with it.
interface ChartRow {
  date: string;
  [series: string]: number | string | null;
}

export function SeriesLineChart({
  series,
  yLabel,
  height = 420,
  valueFormatter,
}: SeriesLineChartProps) {
  const c = useChartColors();
  // Merge the per-series points into one date-keyed dataset. Memoized so it only
  // recomputes when the series actually change (e.g. a scenario toggle), not on
  // every unrelated re-render.
  const data = useMemo(() => {
    const rowsByDate = new Map<string, ChartRow>();
    for (const s of series) {
      for (const point of s.points) {
        let row = rowsByDate.get(point.date);
        if (!row) {
          row = { date: point.date };
          rowsByDate.set(point.date, row);
        }
        row[s.name] = point.value;
      }
    }
    return Array.from(rowsByDate.values()).sort((a, b) => a.date.localeCompare(b.date));
  }, [series]);

  if (series.length === 0 || data.length === 0) {
    return <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-subtle)" }}>No data to plot.</div>;
  }

  return (
    <div>
      {yLabel ? <ChartHeader>{yLabel}</ChartHeader> : null}
      <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
        <CartesianGrid stroke={c.grid} strokeDasharray="3 3" />
        <XAxis dataKey="date" minTickGap={56} tick={{ fontSize: 12, fill: c.font }} stroke={c.axisLine} />
        <YAxis
          width={76}
          tick={{ fontSize: 12, fill: c.font }}
          stroke={c.axisLine}
          tickFormatter={valueFormatter ? (v: number) => valueFormatter(Number(v)) : undefined}
        />
        <Tooltip
          contentStyle={{ background: c.hoverBg, border: `1px solid ${c.hoverBorder}`, color: c.font }}
          labelStyle={{ color: c.font }}
        />
        <Legend wrapperStyle={{ color: c.font }} />
        {series.map((s, index) => {
          // Benchmark lines carry meta={"dash":"dash"} (§4.4) -> render dashed.
          const dashed = Boolean(s.meta?.["dash"]);
          return (
            <Line
              key={s.name}
              type="monotone"
              dataKey={s.name}
              stroke={colorFor(s.name, index)}
              strokeDasharray={dashed ? "6 4" : undefined}
              dot={false}
              strokeWidth={1.5}
              connectNulls={false}
              isAnimationActive={false}
            />
          );
        })}
      </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
