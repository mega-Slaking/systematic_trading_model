/**
 * PlotlyLineChart: a reusable Plotly line chart over the `NamedSeries[]` contract,
 * with optional secondary y-axis (for the tearsheet's rolling vol/Sharpe dual-axis).
 * Closest hover (single curve, per the user's preference), dashed lines from
 * meta.dash, configurable d3 tick formats. Default export so it's `React.lazy`-able,
 * keeping Plotly's bundle code-split (shared with the other Plotly charts).
 */

import type { Data, Layout } from "plotly.js";

import type { NamedSeries } from "../../api/types";
import { plotlyAxisTheme, plotlyBaseLayout, useChartColors } from "../../theme/chartTheme";
import { ChartHeader } from "./ChartHeader";
import { Plot } from "./plotlyComponent";

interface PlotlyLineChartProps {
  series: readonly NamedSeries[];
  yLabel?: string;
  yTickFormat?: string; // d3 format, e.g. "$,.0f" or ".1%"
  secondaryNames?: string[]; // series rendered against the secondary y-axis
  y2Label?: string;
  y2TickFormat?: string;
  height?: number;
  // Horizontal dashed guides (e.g. CFNAI neutral 0, zero yield-curve spread).
  referenceLines?: { value: number; axis?: "y" | "y2" }[];
  // Shaded vertical date bands with their own fill colour (inversion, regimes).
  bands?: { start: string; end: string; color: string }[];
  // Vertical marker lines at specific dates (e.g. confirmed state transitions).
  markers?: { date: string; color?: string }[];
}

export default function PlotlyLineChart({
  series,
  yLabel,
  yTickFormat,
  secondaryNames,
  y2Label,
  y2TickFormat,
  height = 400,
  referenceLines,
  bands,
  markers,
}: PlotlyLineChartProps) {
  const c = useChartColors();
  const axis = plotlyAxisTheme(c);
  const secondary = new Set(secondaryNames ?? []);

  const data: Data[] = series.map((s) => {
    const onY2 = secondary.has(s.name);
    const fmt = onY2 ? y2TickFormat : yTickFormat;
    const yTmpl = fmt ? `%{y:${fmt}}` : "%{y}";
    return {
      type: "scatter",
      mode: "lines",
      name: s.name,
      x: s.points.map((p) => p.date),
      y: s.points.map((p) => p.value),
      yaxis: onY2 ? "y2" : "y",
      line: { width: 1.5, dash: s.meta?.["dash"] ? "dash" : "solid" },
      fill: s.meta?.["fill"] ? (s.meta["fill"] as string) : undefined, // e.g. spread "tozeroy"
      connectgaps: false, // null (a NaN at the API boundary, §6) renders as a gap
      hovertemplate: `%{fullData.name}<br>%{x|%Y-%m-%d}: ${yTmpl}<extra></extra>`,
    };
  }) as Data[];

  const layout: Partial<Layout> = {
    ...plotlyBaseLayout(c),
    // Themed trace colourway (cyan primary on dark/contrast, original blue on light;
    // shared tail keeps multi-series differentiation). Defined in chartTheme.
    colorway: c.colorway,
    autosize: true,
    height,
    margin: { t: 28, r: secondary.size > 0 ? 60 : 16, b: 40, l: 64 },
    xaxis: { ...axis, title: { text: "Date" } },
    yaxis: { ...axis, tickformat: yTickFormat },
    hovermode: "closest",
    showlegend: series.length > 1,
    legend: { orientation: "h", x: 0, xanchor: "left", y: 1.02, yanchor: "bottom", font: { size: 10 } },
  };
  if (secondary.size > 0) {
    // yaxis2 is loosely typed in the bundled @types; assign via a cast.
    (layout as Record<string, unknown>).yaxis2 = {
      ...axis,
      tickformat: y2TickFormat,
      overlaying: "y",
      side: "right",
    };
  }
  const shapes: NonNullable<Layout["shapes"]> = [];
  for (const b of bands ?? []) {
    // Vertical date bands (constant data-meaning colours, not theme chrome).
    shapes.push({
      type: "rect", xref: "x", x0: b.start, x1: b.end, yref: "paper", y0: 0, y1: 1,
      fillcolor: b.color, line: { width: 0 }, layer: "below",
    });
  }
  for (const r of referenceLines ?? []) {
    shapes.push({
      type: "line", xref: "paper", x0: 0, x1: 1, yref: r.axis ?? "y", y0: r.value, y1: r.value,
      line: { color: c.axisLine, width: 1, dash: "dot" }, layer: "below",
    });
  }
  for (const m of markers ?? []) {
    // Vertical transition markers: full-height dotted lines at a date (x as data).
    shapes.push({
      type: "line", xref: "x", x0: m.date, x1: m.date, yref: "paper", y0: 0, y1: 1,
      line: { color: m.color ?? c.axisLine, width: 1, dash: "dot" }, layer: "below",
    });
  }
  if (shapes.length) layout.shapes = shapes;

  // The y-axis label(s) become a header above the chart (dual-axis joins both).
  const header = [yLabel, secondary.size > 0 ? y2Label : undefined].filter(Boolean).join(" · ");

  return (
    <div>
      {header ? <ChartHeader>{header}</ChartHeader> : null}
      <Plot
        data={data}
        layout={layout}
        style={{ width: "100%", height }}
        useResizeHandler
        config={{ responsive: true, displaylogo: false }}
      />
    </div>
  );
}
