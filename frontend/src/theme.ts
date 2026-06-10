/**
 * Theme constants (spec §7.2): colors matching the Streamlit `plotly_white` look.
 * Phase 0 stub; charting phases consume these for trace colors and axes.
 */

export const theme = {
  background: "#ffffff",
  text: "#333333",
  grid: "#e5e5e5",
  // Per-ticker accent colors (TLT long-duration, AGG broad, SHY cash-like).
  tickers: {
    TLT: "#1f77b4",
    AGG: "#ff7f0e",
    SHY: "#2ca02c",
  },
} as const;
