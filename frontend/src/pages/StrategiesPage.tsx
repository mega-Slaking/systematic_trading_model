/**
 * Strategies page (spec endpoint 12, Phase 4): read-only registry introspection —
 * decodes what each opaque scenario name means (knobs from the StrategyConfig).
 * The live strategy is starred. This is a new capability beyond the Streamlit views.
 */

import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import { useStrategies } from "../api/hooks";
import type { StrategySummary } from "../api/types";
import { DataTable, type Column } from "../components/tables/DataTable";
import { formatPercent } from "../lib/format";

const COLUMNS: Column<StrategySummary>[] = [
  { key: "name", header: "Name", render: (r) => (r.is_live ? `★ ${r.name}` : r.name), sortValue: (r) => r.name },
  { key: "starting_weight_source", header: "Source" },
  { key: "cov_method", header: "Cov Method" },
  {
    key: "use_vol_scaling",
    header: "Vol Scaling",
    align: "right",
    render: (r) => (r.use_vol_scaling ? `✓ (p=${r.vol_scaling_power})` : "—"),
    sortValue: (r) => (r.use_vol_scaling ? 1 : 0),
  },
  {
    key: "use_covariance_scaling",
    header: "Cov Scaling",
    align: "right",
    render: (r) => (r.use_covariance_scaling ? "✓" : "—"),
    sortValue: (r) => (r.use_covariance_scaling ? 1 : 0),
  },
  {
    key: "target_portfolio_vol",
    header: "Target Vol",
    align: "right",
    render: (r) => formatPercent(r.target_portfolio_vol),
    sortValue: (r) => r.target_portfolio_vol,
  },
];

export function StrategiesPage() {
  const query = useStrategies();

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Strategies</h2>
      <p style={{ color: "#666", marginTop: "0.25rem" }}>
        The strategy registry — what each scenario name means.
        {query.data ? (
          <>
            {" "}
            Live book: <strong>★ {query.data.live_strategy}</strong>.
          </>
        ) : null}
      </p>

      {query.isLoading ? (
        <Muted>Loading registry…</Muted>
      ) : query.isError ? (
        <Muted tone="error">{errorMessage(query.error)}</Muted>
      ) : (
        <DataTable columns={COLUMNS} rows={query.data?.strategies ?? []} />
      )}
    </div>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.message} (HTTP ${error.status})`;
  return error instanceof Error ? error.message : "Request failed.";
}

function Muted({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return <div style={{ padding: "1rem", color: tone === "error" ? "#b00020" : "#777" }}>{children}</div>;
}
