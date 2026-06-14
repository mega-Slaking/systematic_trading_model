/**
 * Tearsheet page (spec Tab 3, Phase 3): the highest-value view and the one real
 * compute path. A single-scenario picker drives `useTearsheet` (cached), then we
 * render the metric grid, equity/drawdown/rolling charts (Plotly, lazy), the
 * exposure/regime/benchmark tables, and a collapsible raw-rows table.
 */

import { lazy, Suspense, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { useDailyRows, useScenarios, useTearsheet } from "../api/hooks";
import type { TableModel, TearsheetMetricsModel } from "../api/types";
import { MetricGrid, type Metric } from "../components/MetricGrid";
import { DataTable, type Column } from "../components/tables/DataTable";
import { formatCurrency, formatPercent, formatRatio } from "../lib/format";

// Plotly charts, lazy-loaded once and reused for equity/drawdown/rolling so
// Plotly's bundle stays code-split (shared with the NAV/Returns charts).
const PlotlyLineChart = lazy(() => import("../components/charts/PlotlyLineChart"));

// Column-name heuristics for the generic summary tables (the API returns raw
// numbers; these decide $/%/ratio formatting from the column name).
const CURRENCY_COL = /(nav|cost|notional)/i;
const PERCENT_COL = /(^ret$|return|cagr|volatility|drawdown|alpha|tracking_error|weight|turnover|day|concentration|exposure|^value$)/i;
const RATIO_COL = /(ratio|beta|correlation|r_squared|sharpe|sortino|calmar)/i;

function buildMetrics(s: TearsheetMetricsModel): Metric[] {
  return [
    { label: "Total Return", value: s.total_return, format: "percent" },
    { label: "CAGR", value: s.cagr, format: "percent" },
    { label: "Ann. Volatility", value: s.annualized_volatility, format: "percent" },
    { label: "Sharpe", value: s.sharpe, format: "ratio" },
    { label: "Sortino", value: s.sortino, format: "ratio" },
    { label: "Calmar", value: s.calmar, format: "ratio" },
    { label: "Max Drawdown", value: s.max_drawdown, format: "percent" },
    { label: "VaR 95%", value: s.var_95, format: "percent" },
    { label: "CVaR 95%", value: s.cvar_95, format: "percent" },
    { label: "Parametric VaR 95%", value: s.parametric_var_95, format: "percent" },
    { label: "Worst Day", value: s.worst_day, format: "percent" },
    { label: "Best Day", value: s.best_day, format: "percent" },
    { label: "Skew", value: s.skew, format: "ratio" },
    { label: "Excess Kurtosis", value: s.excess_kurtosis, format: "ratio" },
    { label: "Avg Turnover", value: s.avg_turnover, format: "percent" },
    { label: "Daily Hit Rate", value: s.daily_hit_rate, format: "percent" },
    { label: "Payoff Ratio", value: s.payoff_ratio, format: "ratio" },
    { label: "Profit Factor", value: s.profit_factor, format: "ratio" },
    { label: "Avg Win", value: s.avg_win, format: "percent" },
    { label: "Avg Loss", value: s.avg_loss, format: "percent" },
  ];
}

function formatTableCell(column: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number") {
    if (CURRENCY_COL.test(column)) return formatCurrency(value, 0);
    if (PERCENT_COL.test(column)) return formatPercent(value);
    if (RATIO_COL.test(column)) return formatRatio(value);
    if (Number.isInteger(value)) return String(value);
    return formatRatio(value, 4);
  }
  return String(value);
}

function TableModelView({ table }: { table: TableModel }) {
  if (table.rows.length === 0) return <Muted>No rows.</Muted>;
  const columns: Column<Record<string, unknown>>[] = table.columns.map((col) => ({
    key: col,
    header: col,
    align: typeof table.rows[0]?.[col] === "number" ? "right" : "left",
    render: (row) => formatTableCell(col, row[col]),
    sortValue: (row) => {
      const v = row[col];
      return typeof v === "number" || typeof v === "string" ? v : null;
    },
  }));
  return <DataTable columns={columns} rows={table.rows} />;
}

export function TearsheetPage() {
  const scenariosQuery = useScenarios();
  const scenarios = scenariosQuery.data?.scenarios ?? [];

  const [selected, setSelected] = useState<string>("");
  const active = selected || scenarios[0] || "";

  const tearsheet = useTearsheet(active || undefined);
  const daily = useDailyRows(active || undefined, { limit: 50 });

  const summary = tearsheet.data?.summary;

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Tearsheet</h2>

      <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", marginBottom: "1rem" }}>
        <span style={{ color: "var(--text-3)", fontSize: "0.9rem" }}>Scenario:</span>
        <select
          value={active}
          onChange={(e) => setSelected(e.target.value)}
          style={{ padding: "0.35rem 0.5rem", borderRadius: 6, border: "1px solid var(--border-strong)", fontFamily: "ui-monospace, monospace" }}
        >
          {scenarios.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      {summary && (
        <p style={{ color: "var(--text-muted)", margin: "0 0 1rem" }}>
          {summary.scenario_id} | {summary.start_date} → {summary.end_date}
          {tearsheet.data?.regime_match_rate != null && (
            <span> | regime match rate {formatPercent(tearsheet.data.regime_match_rate)}</span>
          )}
        </p>
      )}

      {tearsheet.isLoading ? (
        <Muted>Loading tearsheet…</Muted>
      ) : tearsheet.isError ? (
        <Muted tone="error">{errorMessage(tearsheet.error)}</Muted>
      ) : tearsheet.data && summary ? (
        <>
          <MetricGrid metrics={buildMetrics(summary)} />

          <Suspense fallback={<Muted>Loading charts…</Muted>}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "1rem", marginTop: "1.5rem" }}>
              <ChartCard title="Equity Curve">
                <PlotlyLineChart series={[tearsheet.data.equity_curve]} yLabel="NAV ($)" yTickFormat="$,.0f" height={320} />
              </ChartCard>
              <ChartCard title="Drawdown">
                <PlotlyLineChart series={[tearsheet.data.drawdown_curve]} yLabel="Drawdown" yTickFormat=".1%" height={320} />
              </ChartCard>
            </div>
            {tearsheet.data.rolling_metrics.length > 0 && (
              <ChartCard title="Rolling Volatility & Sharpe">
                <PlotlyLineChart
                  series={tearsheet.data.rolling_metrics}
                  yLabel="Volatility / Return"
                  yTickFormat=".1%"
                  secondaryNames={["Rolling Sharpe"]}
                  y2Label="Sharpe"
                  y2TickFormat=".2f"
                  height={420}
                />
              </ChartCard>
            )}
          </Suspense>

          <TableSection title="Exposure Summary" table={tearsheet.data.exposure_summary} />
          <TableSection title="Regime Summary" table={tearsheet.data.regime_summary} />
          <TableSection title="Benchmark Summary" table={tearsheet.data.benchmark_summary} />

          <details style={{ marginTop: "1.5rem" }}>
            <summary style={{ cursor: "pointer", fontWeight: 600 }}>
              Raw scenario data {daily.data ? `(showing ${daily.data.table.rows.length} of ${daily.data.total_rows})` : ""}
            </summary>
            <div style={{ marginTop: "0.75rem", overflowX: "auto" }}>
              {daily.isLoading ? (
                <Muted>Loading rows…</Muted>
              ) : daily.isError ? (
                <Muted tone="error">{errorMessage(daily.error)}</Muted>
              ) : daily.data ? (
                <TableModelView table={daily.data.table} />
              ) : null}
            </div>
          </details>
        </>
      ) : null}
    </div>
  );
}

function TableSection({ title, table }: { title: string; table: TableModel | null | undefined }) {
  return (
    <section style={{ marginTop: "1.5rem" }}>
      <h3 style={{ marginBottom: "0.5rem" }}>{title}</h3>
      {table ? <TableModelView table={table} /> : <Muted>Not available.</Muted>}
    </section>
  );
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ border: "1px solid var(--border-soft)", borderRadius: 8, padding: "0.75rem" }}>
      <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>{title}</div>
      {children}
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.message} (HTTP ${error.status})`;
  return error instanceof Error ? error.message : "Request failed.";
}

function Muted({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return <div style={{ padding: "1rem", color: tone === "error" ? "var(--danger)" : "var(--text-subtle)" }}>{children}</div>;
}
