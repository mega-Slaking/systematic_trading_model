/**
 * NavChart: the NAV-comparison line chart rendered with Plotly (the richer
 * interactions -- zoom/pan/unified hover -- suit the long NAV time series, and
 * mirror the original Streamlit chart). Consumes the same `NamedSeries[]` contract
 * as the Recharts `SeriesLineChart`; benchmark series carry meta={"dash":"dash"}
 * (§4.4) and render dashed. Default export so it can be `React.lazy`-loaded,
 * keeping Plotly's bundle code-split (shared with the Returns scatter).
 *
 * SVG `scatter` (not WebGL `scattergl`) is used here because the lines need dash
 * support; the trace count is small (scenarios + 3 benchmarks).
 */

import type { Data, Layout } from "plotly.js";

import type { NamedSeries } from "../../api/types";
import { Plot } from "./plotlyComponent";

interface NavChartProps {
  series: readonly NamedSeries[];
  yLabel?: string;
  height?: number;
}

export default function NavChart({ series, yLabel = "NAV ($)", height = 520 }: NavChartProps) {
  const data: Data[] = series.map((s) => {
    const dashed = Boolean(s.meta?.["dash"]);
    return {
      type: "scatter",
      mode: "lines",
      name: s.name.startsWith("Scenario: ") ? s.name.slice(10) : s.name, // strip prefix → compact legend
      x: s.points.map((p) => p.date),
      y: s.points.map((p) => p.value),
      line: { width: 1.5, dash: dashed ? "dash" : "solid" }, // color auto-assigned by Plotly
      connectgaps: false, // null (a NaN at the API boundary, §6) renders as a gap
      hovertemplate: "%{fullData.name}<br>%{x|%Y-%m-%d}: $%{y:,.0f}<extra></extra>",
    };
  }) as Data[];

  const layout: Partial<Layout> = {
    autosize: true,
    height,
    margin: { t: 10, r: 16, b: 40, l: 72 },
    xaxis: { title: { text: "Date" } },
    yaxis: { title: { text: yLabel }, tickformat: "$,.0f" },
    // Show only the curve under the cursor, not every series at this x.
    hovermode: "closest",
    showlegend: true,
    // Compact multi-column legend ABOVE the chart (doubles as the curve toggle):
    // horizontal flow + a fixed entry width packs the long scenario names into a
    // grid, using far less vertical space than a one-per-row legend.
    legend: {
      orientation: "h",
      x: 0,
      xanchor: "left",
      y: 1.02,
      yanchor: "bottom",
      font: { size: 10 },
      entrywidthmode: "pixels",
      entrywidth: 185,
      // ^ valid Plotly 3.x props; cast past the stale @types/plotly.js Legend type.
    } as Layout["legend"],
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
