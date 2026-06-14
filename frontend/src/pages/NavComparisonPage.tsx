/**
 * NAV Comparison page (spec Tab 1): per-scenario NAV lines + dashed buy-and-hold
 * benchmarks (Plotly `NavChart`) + the performance summary table.
 *
 * Curve visibility is driven by the chart legend itself (single-click toggles a
 * curve, double-click isolates one), so there's no separate scenario picker. The
 * full payload is fetched once.
 */

import { lazy, Suspense, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { useNavComparison } from "../api/hooks";
import type { ScenarioSummaryRow } from "../api/types";
import { DataTable, type Column } from "../components/tables/DataTable";
import { formatCurrency, formatPercent } from "../lib/format";

// Plotly NAV chart, lazy-loaded so Plotly's bundle stays code-split (shared with
// the Returns scatter) and the app shell + summary table render immediately.
const NavChart = lazy(() => import("../components/charts/NavChart"));

const SUMMARY_COLUMNS: Column<ScenarioSummaryRow>[] = [
  { key: "scenario_id", header: "Scenario" },
  { key: "final_nav", header: "Final NAV", align: "right", render: (r) => formatCurrency(r.final_nav), sortValue: (r) => r.final_nav },
  { key: "total_return", header: "Total Return", align: "right", render: (r) => formatPercent(r.total_return), sortValue: (r) => r.total_return },
  { key: "max_drawdown", header: "Max Drawdown", align: "right", render: (r) => formatPercent(r.max_drawdown), sortValue: (r) => r.max_drawdown },
  { key: "annualized_volatility", header: "Volatility", align: "right", render: (r) => formatPercent(r.annualized_volatility), sortValue: (r) => r.annualized_volatility },
];

export function NavComparisonPage() {
  const nav = useNavComparison();
  const chartSeries = nav.data ? [...nav.data.scenario_series, ...nav.data.benchmark_series] : [];

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>NAV Comparison</h2>
      <p style={{ color: "var(--text-muted)", marginTop: "0.25rem" }}>
        Scenario NAV curves vs. buy &amp; hold benchmarks (dashed). Click a legend entry to toggle a curve;
        double-click to isolate one.
      </p>

      <section style={{ marginBottom: "2rem" }}>
        {nav.isLoading ? (
          <Status>Loading NAV curves…</Status>
        ) : nav.isError ? (
          <Status tone="error">{errorMessage(nav.error)}</Status>
        ) : (
          <Suspense fallback={<Status>Loading chart…</Status>}>
            <NavChart series={chartSeries} />
          </Suspense>
        )}
      </section>

      <h3 style={{ marginBottom: "0.5rem" }}>Scenario Performance Summary</h3>
      {nav.isLoading ? (
        <Status>Loading summary…</Status>
      ) : nav.isError ? (
        <Status tone="error">{errorMessage(nav.error)}</Status>
      ) : (
        <DataTable columns={SUMMARY_COLUMNS} rows={nav.data?.summary ?? []} />
      )}
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.message} (HTTP ${error.status})`;
  return error instanceof Error ? error.message : "Request failed.";
}

function Status({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return <div style={{ padding: "1.5rem", color: tone === "error" ? "var(--danger)" : "var(--text-muted)" }}>{children}</div>;
}
