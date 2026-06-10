/**
 * Shared, interop-corrected Plotly React component.
 *
 * react-plotly.js is CommonJS. Vite's dep optimizer re-exports it as
 * `export default require_react_plotly()`, so a default import yields the module
 * OBJECT `{ __esModule, default: Component }`, not the component itself -- React
 * then throws "Element type is invalid ... got: object". We unwrap the interop
 * `.default` here, once, for every Plotly-based chart. The `??` fallback keeps the
 * rollup production build working, where the default import is already the
 * component (no extra wrapper).
 *
 * Import this only from lazy-loaded chart modules so Plotly's heavy bundle stays
 * code-split out of the initial load.
 */

import type { ComponentType } from "react";
import PlotDefault from "react-plotly.js";
import type { PlotParams } from "react-plotly.js";

export const Plot = ((PlotDefault as unknown as { default?: ComponentType<PlotParams> }).default ??
  (PlotDefault as unknown as ComponentType<PlotParams>)) as ComponentType<PlotParams>;
