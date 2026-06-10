/**
 * NAV Comparison page (spec Tab 1, Phase 2): per-scenario NAV lines + dashed
 * buy-and-hold benchmark lines (one `SeriesLineChart`) plus the performance
 * summary table (`DataTable`).
 *
 * Perf: the full nav-comparison payload (all scenarios + benchmarks) is fetched
 * ONCE; the `ScenarioSelect` filters which series/rows show **client-side**, so
 * toggling a scenario is instant -- no refetch, no loading flash. (Earlier this
 * keyed the query on the selection, refetching the whole payload on every click.)
 */

import { lazy, Suspense, useMemo, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { useNavComparison, useScenarios } from "../api/hooks";
import type { ScenarioSummaryRow } from "../api/types";
import { ScenarioSelect } from "../components/ScenarioSelect";
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
  const scenariosQuery = useScenarios();
  const allScenarios = scenariosQuery.data?.scenarios ?? [];

  // Fetch the complete payload once; toggling filters it client-side.
  const nav = useNavComparison();

  // `null` = "all" (default); an array = an explicit selection.
  const [selected, setSelected] = useState<string[] | null>(null);
  const effective = selected ?? allScenarios;

  const { chartSeries, summary } = useMemo(() => {
    const shownNames = new Set(effective.map((id) => `Scenario: ${id}`));
    const shownIds = new Set(effective);
    const scenarioSeries = (nav.data?.scenario_series ?? []).filter((s) => shownNames.has(s.name));
    return {
      chartSeries: [...scenarioSeries, ...(nav.data?.benchmark_series ?? [])],
      summary: (nav.data?.summary ?? []).filter((r) => shownIds.has(r.scenario_id)),
    };
  }, [nav.data, effective]);

  const loading = nav.isLoading || scenariosQuery.isLoading;
  const noneSelected = selected !== null && selected.length === 0;

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>NAV Comparison</h2>
      <p style={{ color: "#666", marginTop: "0.25rem" }}>
        Scenario NAV curves vs. buy &amp; hold benchmarks (dashed), with a performance summary.
      </p>

      {allScenarios.length > 0 && (
        <ScenarioSelect scenarios={allScenarios} selected={effective} onChange={setSelected} />
      )}

      <section style={{ marginBottom: "2rem" }}>
        {loading ? (
          <Status>Loading NAV curves…</Status>
        ) : nav.isError ? (
          <Status tone="error">{errorMessage(nav.error)}</Status>
        ) : noneSelected ? (
          <Status>Select at least one scenario.</Status>
        ) : (
          <Suspense fallback={<Status>Loading chart…</Status>}>
            <NavChart series={chartSeries} />
          </Suspense>
        )}
      </section>

      <h3 style={{ marginBottom: "0.5rem" }}>Scenario Performance Summary</h3>
      {loading ? (
        <Status>Loading summary…</Status>
      ) : nav.isError ? (
        <Status tone="error">{errorMessage(nav.error)}</Status>
      ) : (
        <DataTable columns={SUMMARY_COLUMNS} rows={summary} />
      )}
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.message} (HTTP ${error.status})`;
  return error instanceof Error ? error.message : "Request failed.";
}

function Status({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return <div style={{ padding: "1.5rem", color: tone === "error" ? "#b00020" : "#666" }}>{children}</div>;
}
