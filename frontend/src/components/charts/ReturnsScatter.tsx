/**
 * ReturnsScatter (Returns Analysis diagnostic redesign): the daily-return scatter,
 * rendered with Plotly's WebGL `scattergl`. Default export so it can be
 * `React.lazy`-loaded, keeping Plotly's heavy bundle off the initial load.
 *
 * The full scenario grid is shipped once, so showing/hiding a scenario is a pure
 * client-side legend toggle (no refetch). Visibility is owned by React (a `hidden`
 * set) rather than Plotly's internal state, so it survives re-renders and drives
 * the boxplot too: legend click toggles, double-click isolates. Markers are small
 * and semi-transparent, with horizontal reference lines at 0 / ±1% / ±2%.
 *
 * Hover is concise (label / date / return); rich per-point context is fetched on
 * demand when a point is clicked (the drilldown panel).
 */

import type { Data, Layout, LegendClickEvent, PlotMouseEvent } from "plotly.js";

import type { ReturnsDiagnosticSeries } from "../../api/types";
import { Plot } from "./plotlyComponent";

/** A clicked point, surfaced to the page so it can fetch the drilldown detail. */
export interface ScatterPointSelection {
  scenarioId: string;
  scenarioLabel: string;
  date: string;
}

interface ReturnsScatterProps {
  series: readonly ReturnsDiagnosticSeries[]; // the rendered universe (already filtered)
  hidden: ReadonlySet<string>; // scenario ids drawn `legendonly`
  onToggleScenario: (scenarioId: string) => void;
  onIsolateScenario: (scenarioId: string) => void;
  showReferenceLines?: boolean;
  useRawLabels?: boolean; // legend shows raw scenario ids instead of readable labels
  onSelectPoint?: (point: ScatterPointSelection) => void;
  height?: number;
}

const REFERENCE_LEVELS = [0, 0.01, -0.01, 0.02, -0.02];

export default function ReturnsScatter({
  series,
  hidden,
  onToggleScenario,
  onIsolateScenario,
  showReferenceLines = true,
  useRawLabels = false,
  onSelectPoint,
  height = 520,
}: ReturnsScatterProps) {
  const data: Data[] = series.map((s) => ({
    type: "scattergl",
    mode: "markers",
    name: useRawLabels ? s.scenario_id : s.scenario_label,
    x: s.dates,
    y: s.returns,
    visible: hidden.has(s.scenario_id) ? "legendonly" : true,
    marker: { size: 5, opacity: 0.45 },
    hovertemplate: "%{fullData.name}<br>%{x|%Y-%m-%d}<br>%{y:.2%}<extra></extra>",
  })) as Data[];

  const layout: Partial<Layout> = {
    autosize: true,
    height,
    margin: { t: 10, r: 16, b: 40, l: 64 },
    xaxis: { title: { text: "Date" }, type: "date" },
    yaxis: { title: { text: "Daily Return" }, tickformat: ".1%" },
    hovermode: "closest",
    showlegend: true,
    // Compact multi-column legend above the chart (the scenario show/hide control).
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
    shapes: showReferenceLines ? referenceLineShapes() : [],
  };

  // Own legend interactions in React (return false to suppress Plotly's own toggle)
  // so visibility persists across re-renders and the boxplot can mirror it.
  function handleLegendClick(event: Readonly<LegendClickEvent>): boolean {
    const s = series[event.curveNumber];
    if (s) onToggleScenario(s.scenario_id);
    return false;
  }

  function handleLegendDoubleClick(event: Readonly<LegendClickEvent>): boolean {
    const s = series[event.curveNumber];
    if (s) onIsolateScenario(s.scenario_id);
    return false;
  }

  function handleClick(event: Readonly<PlotMouseEvent>) {
    if (!onSelectPoint || !event.points?.length) return;
    const p = event.points[0];
    const s = series[p.curveNumber];
    if (!s) return;
    onSelectPoint({ scenarioId: s.scenario_id, scenarioLabel: s.scenario_label, date: String(p.x) });
  }

  return (
    <Plot
      data={data}
      layout={layout}
      style={{ width: "100%", height }}
      useResizeHandler
      onClick={handleClick}
      onLegendClick={handleLegendClick}
      onLegendDoubleClick={handleLegendDoubleClick}
      config={{ responsive: true, displaylogo: false }}
    />
  );
}

/** Horizontal reference lines at 0 / ±1% / ±2% (zero stronger than the rest). */
function referenceLineShapes(): NonNullable<Layout["shapes"]> {
  return REFERENCE_LEVELS.map((level) => {
    const isZero = level === 0;
    return {
      type: "line" as const,
      xref: "paper" as const,
      x0: 0,
      x1: 1,
      yref: "y" as const,
      y0: level,
      y1: level,
      line: {
        color: isZero ? "#555" : "#d0d0d0",
        width: isZero ? 1.4 : 1,
        dash: isZero ? ("solid" as const) : ("dot" as const),
      },
      layer: "below" as const,
    };
  });
}
