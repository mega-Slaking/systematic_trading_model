/**
 * OutcomeBoxplot (Volatility Features, Phase 9): one box per diagnostic state
 * comparing the *forward-return* distributions that historically followed each
 * state at the selected horizon. The aggregate table answers "what were the
 * summary stats?"; this answers "how do the forward-return distributions differ
 * across states, and how dispersed are they?". Default export so Plotly's bundle
 * stays code-split (shared with the other Plotly charts).
 *
 * Fed the same (non-overlapping by default) per-observation sample the API used
 * for the aggregate table, so the box and the stats describe the same evidence.
 * The box styling itself lives in the shared BaseBoxplot.
 */

import type { StateReturnDistribution } from "../../api/types";
import { volStateBoxColor } from "../../theme/regimeColors";
import { BaseBoxplot, type BoxSeries } from "./BaseBoxplot";

interface OutcomeBoxplotProps {
  distributions: readonly StateReturnDistribution[];
  horizon: string;
  height?: number;
}

export default function OutcomeBoxplot({ distributions, horizon, height = 360 }: OutcomeBoxplotProps) {
  const series: BoxSeries[] = distributions.map((d) => ({
    name: `${d.state} (n=${d.effective_observations})`,
    y: d.returns,
    color: volStateBoxColor(d.state),
  }));

  return (
    <BaseBoxplot series={series} header={`${horizon} forward return`} height={height} marginBottom={96} />
  );
}
