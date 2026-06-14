/**
 * Chart colour theming for the toggle's three modes.
 *
 * Plotly and Recharts need concrete colour values (not CSS variables), and must
 * re-render when the mode changes — so charts read these via `useChartColors()`,
 * which subscribes to the theme context. The canvas itself is kept transparent
 * so the chart inherits whatever themed background sits behind it (page or card);
 * only the foreground colours (font, grid, axes, hover) are set per mode.
 *
 * Data-trace colours are intentionally NOT themed here — series identity (TLT vs
 * AGG vs SHY, the scenario palette) stays constant across modes.
 */

import type { Layout } from "plotly.js";

import { useTheme, type ThemeMode } from "./ThemeContext";

export interface ChartColors {
  font: string;
  grid: string;
  axisLine: string;
  zeroLine: string;
  hoverBg: string;
  hoverBorder: string;
  modebar: string;
  modebarActive: string;
}

const PALETTES: Record<ThemeMode, ChartColors> = {
  light: {
    font: "#333333",
    grid: "#e5e5e5",
    axisLine: "#d0d0d0",
    zeroLine: "#cccccc",
    hoverBg: "#ffffff",
    hoverBorder: "#d1d5db",
    modebar: "#888888",
    modebarActive: "#1f77b4",
  },
  dark: {
    font: "#e6e6e6",
    grid: "#333333",
    axisLine: "#4a4a4a",
    zeroLine: "#3a3a3a",
    hoverBg: "#1f1f1f",
    hoverBorder: "#3d3d3d",
    modebar: "#9a9a9a",
    modebarActive: "#4ea3e0",
  },
  contrast: {
    font: "#00b3ff",
    grid: "#123a4a",
    axisLine: "#00b3ff",
    zeroLine: "#005f87",
    hoverBg: "#000000",
    hoverBorder: "#00b3ff",
    modebar: "#00b3ff",
    modebarActive: "#33c4ff",
  },
};

/** Chart colours for the active theme mode (re-renders the caller on change). */
export function useChartColors(): ChartColors {
  return PALETTES[useTheme().mode];
}

/**
 * Common Plotly layout theming: a transparent canvas (so the chart matches the
 * page/card background) plus themed default font, hover label, and modebar.
 */
export function plotlyBaseLayout(c: ChartColors): Partial<Layout> {
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: c.font },
    hoverlabel: { bgcolor: c.hoverBg, bordercolor: c.hoverBorder, font: { color: c.font } },
    modebar: { color: c.modebar, activecolor: c.modebarActive, bgcolor: "rgba(0,0,0,0)" },
  };
}

/** Per-axis grid/line/zeroline colours — spread into each Plotly axis object. */
export function plotlyAxisTheme(c: ChartColors) {
  return {
    gridcolor: c.grid,
    linecolor: c.axisLine,
    zerolinecolor: c.zeroLine,
    tickcolor: c.axisLine,
  };
}
