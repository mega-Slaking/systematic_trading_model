/**
 * BaseBoxplot: the shared Plotly box-plot skeleton (theme, layout, hover, Plot
 * wiring) behind ReturnsBoxplot and OutcomeBoxplot. Callers pass only their
 * per-series name/values (and an optional per-box colour) plus the header — the
 * one place the box styling lives, so the two charts can't drift apart.
 *
 * NOT a default export and NOT lazy itself: the two concrete charts stay the
 * code-split entry points (default exports) and import this synchronously, so it
 * rides along in their already-shared Plotly chunk.
 */

import type { Data, Layout } from "plotly.js";

import { plotlyAxisTheme, plotlyBaseLayout, useChartColors } from "../../theme/chartTheme";
import { useTheme } from "../../theme/ThemeContext";
import { ChartHeader } from "./ChartHeader";
import { Plot } from "./plotlyComponent";

// Default Plotly palette tail (D3 category10 minus its leading blue); only the
// primary box's colour differs between modes. Boxes that pass an explicit `color`
// (e.g. OutcomeBoxplot's per-state fills) override the colourway and are unaffected.
const PALETTE_TAIL = ["#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"];

export interface BoxSeries {
  name: string;
  y: readonly (number | null)[];
  /** Optional per-box colour (marker/line/fill). Omit to use Plotly's default palette. */
  color?: string;
}

interface BaseBoxplotProps {
  series: readonly BoxSeries[];
  header: string;
  /** y-axis tick format (default ".1%") and hover format (default ".2%"). */
  tickFormat?: string;
  hoverFormat?: string;
  height?: number;
  /** Bottom margin — widen for long, rotated x labels (default 80). */
  marginBottom?: number;
}

export function BaseBoxplot({
  series,
  header,
  tickFormat = ".1%",
  hoverFormat = ".2%",
  height = 360,
  marginBottom = 80,
}: BaseBoxplotProps) {
  const c = useChartColors();
  const { mode } = useTheme();
  const axis = plotlyAxisTheme(c);
  // Primary box is cyan on the dark/contrast canvases, the original Plotly blue on light.
  const primaryColor = mode === "light" ? "#1f77b4" : "#06b6d4";

  const data: Data[] = series.map((s) => ({
    type: "box",
    name: s.name,
    y: s.y,
    boxpoints: "outliers",
    marker: { size: 3, opacity: 0.5, ...(s.color ? { color: s.color } : {}) },
    ...(s.color ? { line: { color: s.color }, fillcolor: s.color } : {}),
    hovertemplate: `%{y:${hoverFormat}}<extra>%{fullData.name}</extra>`,
  })) as Data[];

  const layout: Partial<Layout> = {
    ...plotlyBaseLayout(c),
    // Mode-dependent primary box colour (cyan on dark/contrast, original blue on light);
    // the rest of the default palette follows. Explicit per-box colours override this.
    colorway: [primaryColor, ...PALETTE_TAIL],
    autosize: true,
    height,
    margin: { t: 10, r: 16, b: marginBottom, l: 64 },
    yaxis: { ...axis, tickformat: tickFormat, zeroline: true },
    xaxis: { ...axis, automargin: true },
    hovermode: "closest",
    showlegend: false,
  };

  return (
    <div>
      <ChartHeader>{header}</ChartHeader>
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
