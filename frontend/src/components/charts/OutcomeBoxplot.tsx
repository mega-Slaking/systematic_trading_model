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
import { BaseBoxplot, type BoxSeries } from "./BaseBoxplot";

interface OutcomeBoxplotProps {
  distributions: readonly StateReturnDistribution[];
  horizon: string;
  height?: number;
}

/** Data-meaning fill per diagnostic state (constant across themes, aligned with the page badges). */
function stateColor(state: string): string {
  switch (state) {
    case "Shock":
      return "rgba(220,38,38,0.55)";
    case "Stress Expansion":
      return "rgba(220,38,38,0.40)";
    case "Persistent Stress":
      return "rgba(234,88,12,0.45)";
    case "Early Expansion":
      return "rgba(217,119,6,0.45)";
    case "Normalisation":
      return "rgba(37,99,235,0.45)";
    case "Calm":
      return "rgba(16,185,129,0.40)";
    default: // Unknown
      return "rgba(148,163,184,0.40)";
  }
}

export default function OutcomeBoxplot({ distributions, horizon, height = 360 }: OutcomeBoxplotProps) {
  const series: BoxSeries[] = distributions.map((d) => ({
    name: `${d.state} (n=${d.effective_observations})`,
    y: d.returns,
    color: stateColor(d.state),
  }));

  return (
    <BaseBoxplot series={series} header={`${horizon} forward return`} height={height} marginBottom={96} />
  );
}
