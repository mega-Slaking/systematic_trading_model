/**
 * Volatility Features page (spec Tab 5, Phase 4): per-ticker annualized-vol lines
 * + the latest-values table. The full per-ticker series are fetched once; the
 * method chips toggle which lines show **client-side** (no refetch).
 */

import { lazy, Suspense, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { useVolatilityFeatures, useVolatilityLatest } from "../api/hooks";
import type { VolLatestRow } from "../api/types";
import { DataTable, type Column } from "../components/tables/DataTable";
import { formatPercent } from "../lib/format";

const PlotlyLineChart = lazy(() => import("../components/charts/PlotlyLineChart"));

const VOL_METHODS: Record<string, string> = {
  rolling_20: "Rolling 20d",
  rolling_60: "Rolling 60d",
  ewma_94: "EWMA λ=0.94",
  ewma_97: "EWMA λ=0.97",
  garch: "GARCH(1,1)",
};

const LATEST_COLUMNS: Column<VolLatestRow>[] = [
  { key: "ticker", header: "Ticker" },
  { key: "date", header: "As of" },
  ...Object.entries(VOL_METHODS).map(
    ([key, label]): Column<VolLatestRow> => ({
      key,
      header: label,
      align: "right",
      render: (r) => formatPercent(r[key as keyof VolLatestRow] as number | null),
      sortValue: (r) => r[key as keyof VolLatestRow] as number | null,
    }),
  ),
];

export function VolatilityPage() {
  const latest = useVolatilityLatest();
  const tickers = (latest.data?.rows ?? []).map((r) => r.ticker);

  const [ticker, setTicker] = useState<string>("");
  const activeTicker = ticker || (tickers.includes("TLT") ? "TLT" : tickers[0]) || "";

  const vol = useVolatilityFeatures(activeTicker || undefined);
  const available = vol.data?.available_methods ?? [];

  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const shownSeries = (vol.data?.series ?? []).filter(
    (s) => !hidden.has((s.meta?.["method"] as string | undefined) ?? s.name),
  );

  function toggleMethod(method: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(method)) next.delete(method);
      else next.add(method);
      return next;
    });
  }

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Volatility Features</h2>
      <p style={{ color: "var(--text-muted)", marginTop: "0.25rem" }}>
        Point-in-time annualized volatility per asset (lagged one day — no lookahead).
      </p>

      <div style={{ display: "flex", gap: "1.5rem", alignItems: "center", flexWrap: "wrap", marginBottom: "1rem" }}>
        <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ color: "var(--text-3)", fontSize: "0.9rem" }}>Asset:</span>
          <select value={activeTicker} onChange={(e) => setTicker(e.target.value)} style={{ padding: "0.35rem 0.5rem", borderRadius: 6, border: "1px solid var(--border-strong)" }}>
            {tickers.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
          {available.map((m) => {
            const on = !hidden.has(m);
            return (
              <button
                key={m}
                type="button"
                onClick={() => toggleMethod(m)}
                style={{
                  padding: "0.2rem 0.55rem", borderRadius: 6, fontSize: "0.8rem", cursor: "pointer",
                  border: `1px solid ${on ? "var(--accent)" : "var(--border-strong)"}`,
                  background: on ? "var(--accent-bg)" : "var(--surface)", color: on ? "var(--accent)" : "var(--text-muted)",
                }}
              >
                {VOL_METHODS[m] ?? m}
              </button>
            );
          })}
        </div>
      </div>

      <section style={{ marginBottom: "2rem" }}>
        {vol.isLoading ? (
          <Muted>Loading volatility…</Muted>
        ) : vol.isError ? (
          <Muted tone="error">{errorMessage(vol.error)}</Muted>
        ) : (
          <Suspense fallback={<Muted>Loading chart…</Muted>}>
            <PlotlyLineChart series={shownSeries} yLabel="Annualized volatility" yTickFormat=".0%" height={460} />
          </Suspense>
        )}
      </section>

      <h3 style={{ marginBottom: "0.5rem" }}>Latest values</h3>
      {latest.isLoading ? (
        <Muted>Loading…</Muted>
      ) : latest.isError ? (
        <Muted tone="error">{errorMessage(latest.error)}</Muted>
      ) : (
        <DataTable columns={LATEST_COLUMNS} rows={latest.data?.rows ?? []} />
      )}
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
