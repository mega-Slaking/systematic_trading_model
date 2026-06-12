/**
 * ReturnsScatter (spec §7.1): the dense daily-return scatter, rendered with
 * Plotly's WebGL `scattergl` -- the one view the spec hands to Plotly instead of
 * Recharts (tens of thousands of points across scenarios). Default export so it
 * can be `React.lazy`-loaded, keeping Plotly's heavy bundle off the initial load.
 *
 * Consumes the columnar `ReturnsScatterSeries` (parallel `dates`/`returns`)
 * straight from endpoint 3 -- no per-point object allocation.
 */

import type { Data, Layout } from "plotly.js";

import type { ReturnsScatterSeries } from "../../api/types";
import { Plot } from "./plotlyComponent";

interface ReturnsScatterProps {
  series: readonly ReturnsScatterSeries[];
  height?: number;
}

export default function ReturnsScatter({ series, height = 560 }: ReturnsScatterProps) {
  const data: Data[] = series.map((s) => ({
    type: "scattergl",
    mode: "markers",
    name: s.scenario_id,
    x: s.dates,
    y: s.returns,
    marker: { size: 4, opacity: 0.6 },
  })) as Data[];

  const layout: Partial<Layout> = {
    autosize: true,
    height,
    margin: { t: 10, r: 16, b: 40, l: 64 },
    xaxis: { title: { text: "Date" } },
    yaxis: { title: { text: "Daily Return" }, tickformat: ".1%" },
    hovermode: "closest",
    showlegend: true,
    // Compact multi-column legend above the chart (doubles as the scenario toggle).
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
