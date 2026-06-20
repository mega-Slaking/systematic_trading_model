/**
 * Regime / state shading palettes — the single source for the coloured chart
 * fills that denote a *diagnostic regime or state* (not chrome, and not theme
 * CSS-var tokens). Two pages share these: the Volatility Features confirmed-state
 * shading + forward-return boxplot, and the ETFs-vs-Macro regime timeline.
 *
 * These are deliberately constant *data-meaning* colours (a "Shock" band is the
 * same red regardless of brand theme) with one exception: high-contrast mode
 * swaps the subtle fills for vivid, maximally-distinct neon hues so the regimes
 * read on a black canvas. Centralised here so the two pages can't drift.
 */

import type { ThemeMode } from "./ThemeContext";

// --------------------------------------------------------------------------- //
// Volatility confirmed-state shading (the annualised-vol chart's bands)
// --------------------------------------------------------------------------- //

/**
 * Faint shading fill per notable confirmed state; Calm returns null (unshaded)
 * to keep the chart's baseline clean. High-contrast mode swaps the subtle palette
 * for vivid neon fills (blue avoided — the contrast theme's axes are electric blue).
 */
export function volStateBandColor(state: string, mode: ThemeMode): string | null {
  if (mode === "contrast") {
    switch (state) {
      case "Shock":
        return "rgba(255,40,40,0.55)"; // neon red
      case "Stress Expansion":
        return "rgba(255,16,160,0.50)"; // hot pink
      case "Persistent Stress":
        return "rgba(255,145,0,0.52)"; // neon orange
      case "Early Expansion":
        return "rgba(240,240,20,0.45)"; // neon yellow
      case "Normalisation":
        return "rgba(180,90,255,0.48)"; // neon purple (clear of the electric-blue axis)
      case "Unknown":
        return "rgba(57,255,20,0.42)"; // neon green
      default: // Calm
        return null;
    }
  }
  switch (state) {
    case "Shock":
      return "rgba(220,38,38,0.20)";
    case "Stress Expansion":
      return "rgba(220,38,38,0.11)";
    case "Persistent Stress":
      return "rgba(234,88,12,0.11)";
    case "Early Expansion":
      return "rgba(217,119,6,0.09)";
    case "Normalisation":
      return "rgba(37,99,235,0.09)";
    case "Unknown":
      return "rgba(148,163,184,0.12)";
    default: // Calm
      return null;
  }
}

/** Solid-ish box fill per diagnostic state for the forward-return boxplot. */
export function volStateBoxColor(state: string): string {
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

// --------------------------------------------------------------------------- //
// Macro regime timeline shading (ETFs-vs-Macro page)
// --------------------------------------------------------------------------- //

// Base RGB per regime label; bands use low alpha, legend swatches higher.
const MACRO_REGIME_RGB: Record<string, string> = {
  "Stable Growth": "120, 120, 120",
  "Inflationary Tightening": "214, 39, 40",
  "Disinflationary Slowdown": "31, 119, 180",
  "Stagflation Risk": "148, 0, 33",
  "Easing Transition": "44, 160, 44",
};
const ENGINE_REGIME_RGB: Record<string, string> = {
  "No duration support": "120, 120, 120",
  "Supports duration": "44, 160, 44",
};

// High-contrast neon variants (blue avoided — contrast axes are electric blue).
const MACRO_REGIME_RGB_CONTRAST: Record<string, string> = {
  "Stable Growth": "240, 240, 20", // neon yellow
  "Inflationary Tightening": "255, 40, 40", // neon red
  "Disinflationary Slowdown": "180, 90, 255", // neon purple
  "Stagflation Risk": "255, 16, 160", // hot pink
  "Easing Transition": "57, 255, 20", // neon green
};
const ENGINE_REGIME_RGB_CONTRAST: Record<string, string> = {
  "No duration support": "255, 145, 0", // neon orange
  "Supports duration": "57, 255, 20", // neon green
};

/** Yield-curve inversion band fill (constant across themes). */
export const INVERSION_BAND = "rgba(214, 39, 40, 0.10)";

/** The base-RGB map for the active regime overlay + theme mode (keys are labels). */
export function regimeRgbMap(useEngine: boolean, mode: ThemeMode): Record<string, string> {
  const contrast = mode === "contrast";
  if (useEngine) return contrast ? ENGINE_REGIME_RGB_CONTRAST : ENGINE_REGIME_RGB;
  return contrast ? MACRO_REGIME_RGB_CONTRAST : MACRO_REGIME_RGB;
}
