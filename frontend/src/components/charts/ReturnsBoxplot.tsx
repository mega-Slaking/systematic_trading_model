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

import type { ReturnsDistributionSeries } from "../../api/types";
import { BaseBoxplot, type BoxSeries } from "./BaseBoxplot";

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
  // Box styling now lives in the shared BaseBoxplot; this maps scenarios -> boxes.
  const series: BoxSeries[] = distribution.map((s) => ({
    name: useRawLabels ? s.scenario_id : s.scenario_label,
    y: s.returns,
  }));

  return <BaseBoxplot series={series} header="Daily Return" height={height} />;
}
