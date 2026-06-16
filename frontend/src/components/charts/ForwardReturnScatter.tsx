/**
 * ForwardReturnScatter: a Δ-macro (x) vs subsequent-ETF-return (y) scatter for the
 * explorer's "Scatter vs forward return" mode. Default export so Plotly stays
 * code-split (shared chunk). Zero reference lines on both axes; descriptive only —
 * no trend line is drawn, to avoid implying a fitted relationship.
 *
 * Unlike the time-series line charts (which moved their y-label to a header), a
 * scatter needs both axis titles to be legible, so they are kept here.
 */

import type { Data, Layout } from "plotly.js";

import { plotlyAxisTheme, plotlyBaseLayout, useChartColors } from "../../theme/chartTheme";
import { Plot } from "./plotlyComponent";

interface ScatterPoint {
  date: string;
  x: number;
  y: number;
}

interface ForwardReturnScatterProps {
  points: readonly ScatterPoint[];
  xLabel: string;
  xTickFormat?: string;
  yLabel: string;
  height?: number;
}

export default function ForwardReturnScatter({
  points,
  xLabel,
  xTickFormat,
  yLabel,
  height = 420,
}: ForwardReturnScatterProps) {
  const c = useChartColors();
  const axis = plotlyAxisTheme(c);

  const data: Data[] = [
    {
      type: "scattergl",
      mode: "markers",
      x: points.map((p) => p.x),
      y: points.map((p) => p.y),
      text: points.map((p) => p.date),
      marker: { size: 6, opacity: 0.5 },
      hovertemplate: `%{text}<br>${xLabel}: %{x}<br>${yLabel}: %{y:.1%}<extra></extra>`,
    },
  ] as Data[];

  const layout: Partial<Layout> = {
    ...plotlyBaseLayout(c),
    autosize: true,
    height,
    margin: { t: 16, r: 16, b: 48, l: 64 },
    xaxis: { ...axis, title: { text: xLabel }, tickformat: xTickFormat },
    yaxis: { ...axis, title: { text: yLabel }, tickformat: ".0%" },
    hovermode: "closest",
    showlegend: false,
    shapes: [
      { type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: 0, y1: 0, line: { color: c.axisLine, width: 1, dash: "dot" }, layer: "below" },
      { type: "line", yref: "paper", y0: 0, y1: 1, xref: "x", x0: 0, x1: 0, line: { color: c.axisLine, width: 1, dash: "dot" }, layer: "below" },
    ] as Layout["shapes"],
  };

  return (
    <Plot
      data={data}
      layout={layout}
      style={{ width: "100%", height }}
      useResizeHandler
      config={{ responsive: true, displaylogo: false }}
    />
  );
}
