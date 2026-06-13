/**
 * ReturnsBoxplot (Returns Analysis diagnostic redesign): one box per selected
 * scenario comparing daily-return distributions (median / IQR / whiskers /
 * outliers). The scatter answers "*when* did returns happen?"; this answers "how
 * do the selected distributions *differ*?". Default export so Plotly's bundle
 * stays code-split (shared with the other Plotly charts).
 *
 * Fed the full date-range distribution (not the chart's outlier filter) so the
 * box statistics stay meaningful.
 */

import type { Data, Layout } from "plotly.js";

import type { ReturnsDistributionSeries } from "../../api/types";
import { Plot } from "./plotlyComponent";

interface ReturnsBoxplotProps {
  distribution: readonly ReturnsDistributionSeries[];
  useRawLabels?: boolean;
  height?: number;
}

export default function ReturnsBoxplot({
  distribution,
  useRawLabels = false,
  height = 360,
}: ReturnsBoxplotProps) {
  const data: Data[] = distribution.map((s) => ({
    type: "box",
    name: useRawLabels ? s.scenario_id : s.scenario_label,
    y: s.returns,
    boxpoints: "outliers",
    marker: { size: 3, opacity: 0.5 },
    hovertemplate: "%{y:.2%}<extra>%{fullData.name}</extra>",
  })) as Data[];

  const layout: Partial<Layout> = {
    autosize: true,
    height,
    margin: { t: 10, r: 16, b: 80, l: 64 },
    yaxis: { title: { text: "Daily Return" }, tickformat: ".1%", zeroline: true },
    xaxis: { automargin: true },
    hovermode: "closest",
    showlegend: false,
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
