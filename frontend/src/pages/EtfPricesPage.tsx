/**
 * ETF Prices page (spec Tab 4, Phase 1): the first end-to-end vertical slice.
 *
 * Close-price lines (`SeriesLineChart`) + a price-statistics table (`DataTable`),
 * fed by the typed `useEtfPrices` / `useEtfPriceStats` hooks. All display
 * formatting is client-side (§4.1) -- the API returns raw numbers; a `null`
 * (e.g. the NaN-close latest row) renders as an em dash via the formatters.
 */

import { type ReactNode } from "react";

import { ApiError } from "../api/client";
import { useEtfPrices, useEtfPriceStats } from "../api/hooks";
import type { PriceStat } from "../api/types";
import { SeriesLineChart } from "../components/charts/SeriesLineChart";
import { DataTable, type Column } from "../components/tables/DataTable";
import { formatCurrency, formatPercent } from "../lib/format";

const STAT_COLUMNS: Column<PriceStat>[] = [
  { key: "ticker", header: "Ticker" },
  { key: "first_close", header: "First Close", align: "right", render: (r) => formatCurrency(r.first_close, 2), sortValue: (r) => r.first_close },
  { key: "last_close", header: "Last Close", align: "right", render: (r) => formatCurrency(r.last_close, 2), sortValue: (r) => r.last_close },
  { key: "min_close", header: "Min", align: "right", render: (r) => formatCurrency(r.min_close, 2), sortValue: (r) => r.min_close },
  { key: "max_close", header: "Max", align: "right", render: (r) => formatCurrency(r.max_close, 2), sortValue: (r) => r.max_close },
  { key: "total_return", header: "Total Return", align: "right", render: (r) => formatPercent(r.total_return), sortValue: (r) => r.total_return },
];

export function EtfPricesPage() {
  const prices = useEtfPrices();
  const stats = useEtfPriceStats();

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Historical ETF Prices</h2>
      <p style={{ color: "#666", marginTop: "0.25rem" }}>Daily closing prices for TLT, AGG, and SHY.</p>

      <section style={{ marginBottom: "2rem" }}>
        {prices.isLoading ? (
          <Status>Loading prices…</Status>
        ) : prices.isError ? (
          <Status tone="error">{errorMessage(prices.error)}</Status>
        ) : (
          <SeriesLineChart
            series={prices.data?.series ?? []}
            yLabel="Close ($)"
            valueFormatter={(v) => formatCurrency(v, 0)}
          />
        )}
      </section>

      <h3 style={{ marginBottom: "0.5rem" }}>Price Statistics</h3>
      {stats.isLoading ? (
        <Status>Loading statistics…</Status>
      ) : stats.isError ? (
        <Status tone="error">{errorMessage(stats.error)}</Status>
      ) : (
        <DataTable columns={STAT_COLUMNS} rows={stats.data?.stats ?? []} />
      )}
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.message} (HTTP ${error.status})`;
  return error instanceof Error ? error.message : "Request failed.";
}

function Status({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return (
    <div style={{ padding: "1.5rem", color: tone === "error" ? "#b00020" : "#666" }}>{children}</div>
  );
}
