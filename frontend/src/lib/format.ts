/**
 * Display formatters (spec §4.1, §7.2).
 *
 * The API returns raw numbers (returns as decimal fractions, NAV as plain
 * dollars); all human formatting that Streamlit did inline (`f"{x:.2%}"`,
 * `f"${x:,.0f}"`) lives here, client-side, so values stay machine-usable over
 * the wire. `null` (a NaN that became `null` at the API boundary, §6) renders as
 * an em dash.
 */

const DASH = "—";

/** Format a decimal fraction as a percentage, e.g. 0.0123 -> "1.23%". */
export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  return `${(value * 100).toFixed(digits)}%`;
}

/** Format a dollar amount, e.g. 1000000 -> "$1,000,000". */
export function formatCurrency(value: number | null | undefined, digits = 0): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Format a plain ratio (Sharpe, etc.), e.g. 1.2345 -> "1.23". */
export function formatRatio(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return DASH;
  return value.toFixed(digits);
}
