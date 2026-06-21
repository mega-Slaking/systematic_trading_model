/**
 * Strategies page (spec endpoint 12 + the Phase 5 backtest trigger): read-only
 * registry introspection — decodes what each opaque scenario name means — plus a
 * "Run backtest" panel that triggers a run (endpoint 13), polls it (endpoint 14),
 * and invalidates the analytics queries on completion so every view refreshes.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import {
  useCancelBacktest,
  useJob,
  useResetLiveStrategy,
  useSetLiveStrategy,
  useStrategies,
  useTriggerBacktest,
} from "../api/hooks";
import type { StrategySummary } from "../api/types";
import { DataTable, type Column } from "../components/tables/DataTable";
import { formatPercent } from "../lib/format";

// The non-interactive columns; the live-star column is built in the component
// because it needs the selection mutation + pending state.
const STATIC_COLUMNS: Column<StrategySummary>[] = [
  { key: "name", header: "Name", sortValue: (r) => r.name },
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
  const setLive = useSetLiveStrategy();
  const reset = useResetLiveStrategy();
  const mutating = setLive.isPending || reset.isPending;

  // Star column: filled ★ marks the live book; clicking an empty ☆ makes that row live.
  const liveColumn: Column<StrategySummary> = {
    key: "is_live",
    header: "Live",
    sortValue: (r) => (r.is_live ? 0 : 1), // live first when sorted
    render: (r) => (
      <button
        type="button"
        className="icon-button"
        onClick={() => {
          if (!r.is_live) setLive.mutate(r.name);
        }}
        disabled={mutating || r.is_live}
        title={r.is_live ? "Current live book" : `Make “${r.name}” the live book`}
        aria-label={r.is_live ? `${r.name} is the live book` : `Set ${r.name} as the live book`}
        style={{
          border: "none",
          background: "none",
          padding: "0 0.2rem",
          fontSize: "1.05rem",
          lineHeight: 1,
          color: r.is_live ? "var(--star-live)" : "var(--star-empty)",
          cursor: r.is_live ? "default" : mutating ? "wait" : "pointer",
        }}
      >
        {r.is_live ? "★" : "☆"}
      </button>
    ),
  };

  const columns = [liveColumn, ...STATIC_COLUMNS];
  const mutationError = setLive.error ?? reset.error;

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Strategies</h2>
      <p style={{ color: "var(--text-muted)", marginTop: "0.25rem" }}>
        The strategy registry.
        <br />
        Click the ☆ of a row to choose that strategy for live run trades.
        {query.data ? (
          <>
            <br />
            Live book: <strong>★ {query.data.live_strategy}</strong>
            {query.data.is_overridden ? (
              <>
                {" "}
                <span style={{ color: "var(--text-subtle)" }}>
                  (overridden from default <code>{query.data.default_strategy}</code>)
                </span>{" "}
                <button
                  type="button"
                  onClick={() => reset.mutate()}
                  disabled={mutating}
                  style={{
                    border: "1px solid var(--border-strong)",
                    background: "var(--surface)",
                    color: "var(--control-emphasis-text)",
                    borderRadius: 6,
                    padding: "0.1rem 0.5rem",
                    fontSize: "0.8rem",
                    cursor: mutating ? "wait" : "pointer",
                  }}
                >
                  Reset to default
                </button>
              </>
            ) : null}
            .
          </>
        ) : null}
      </p>

      {mutationError ? (
        <Muted tone="error">{errorMessage(mutationError)}</Muted>
      ) : null}

      <BacktestRunner />

      {query.isLoading ? (
        <Muted>Loading registry…</Muted>
      ) : query.isError ? (
        <Muted tone="error">{errorMessage(query.error)}</Muted>
      ) : (
        <DataTable columns={columns} rows={query.data?.strategies ?? []} />
      )}
    </div>
  );
}

function BacktestRunner() {
  const queryClient = useQueryClient();
  const trigger = useTriggerBacktest();
  const cancel = useCancelBacktest();
  const [jobId, setJobId] = useState<string | undefined>(undefined);
  const job = useJob(jobId);

  const data = job.data;
  const status = data?.status;
  const active = trigger.isPending || status === "queued" || status === "running";

  // On the first transition to "done", refetch every analytics query so the new
  // backtest data shows up everywhere.
  const prevStatus = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (status === "done" && prevStatus.current !== "done") {
      void queryClient.invalidateQueries();
    }
    prevStatus.current = status;
  }, [status, queryClient]);

  function run() {
    trigger.mutate(undefined, { onSuccess: (created) => setJobId(created.job_id) });
  }

  const total = data?.progress_total ?? null;
  const current = data?.progress_current ?? null;
  const pct = total && total > 0 && current != null ? Math.round((current / total) * 100) : null;

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "0.85rem 1rem", marginBottom: "1.25rem", background: "var(--surface-raised)" }}>
      <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
        <button
          type="button"
          onClick={run}
          disabled={active}
          style={{
            padding: "0.45rem 0.9rem",
            borderRadius: 6,
            border: "1px solid var(--accent)",
            background: active ? "var(--accent-disabled)" : "var(--accent)",
            color: "var(--on-accent)",
            fontWeight: 600,
            cursor: active ? "not-allowed" : "pointer",
          }}
        >
          {active ? "Running…" : "Run backtest"}
        </button>

        {active && jobId && (
          <button
            type="button"
            onClick={() => cancel.mutate(jobId)}
            disabled={cancel.isPending}
            style={{
              padding: "0.45rem 0.8rem",
              borderRadius: 6,
              border: "1px solid var(--danger)",
              background: "var(--surface)",
              color: "var(--danger)",
              fontWeight: 600,
              cursor: cancel.isPending ? "not-allowed" : "pointer",
            }}
          >
            {cancel.isPending ? "Cancelling…" : "Cancel"}
          </button>
        )}

        <span style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
          Re-runs the full strategy registry (~minutes, runs in a subprocess) and rewrites the persisted results.
        </span>
      </div>

      {status === "running" && (
        <div style={{ marginTop: "0.7rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8rem", color: "var(--text-3)", marginBottom: "0.25rem" }}>
            <span>{data?.progress_strategy ? `Running: ${data.progress_strategy}` : "Preparing… (building volatility surface)"}</span>
            <span>{total != null && current != null ? `${current} / ${total}` : ""}</span>
          </div>
          <div style={{ height: 8, background: "var(--border-track)", borderRadius: 4, overflow: "hidden" }}>
            <div style={{ width: pct != null ? `${pct}%` : "12%", height: "100%", background: "var(--accent)", transition: "width 0.4s ease" }} />
          </div>
        </div>
      )}

      {(status === "queued" || status === "done" || status === "cancelled" || status === "error" || trigger.isError || cancel.isError) && (
        <div style={{ marginTop: "0.6rem" }}>
          {trigger.isError && <StatusLine tone="error">{errorMessage(trigger.error)}</StatusLine>}
          {cancel.isError && <StatusLine tone="error">{errorMessage(cancel.error)}</StatusLine>}
          {status === "queued" && <StatusLine>Queued…</StatusLine>}
          {status === "done" && (
            <StatusLine tone="ok">
              Done — {data?.scenario_ids_written?.length ?? 0} scenarios written. Views refreshed.
            </StatusLine>
          )}
          {status === "cancelled" && <StatusLine>Cancelled.</StatusLine>}
          {status === "error" && <StatusLine tone="error">Failed: {data?.detail}</StatusLine>}
        </div>
      )}
    </div>
  );
}

function StatusLine({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "ok" | "error" }) {
  const color = tone === "error" ? "var(--danger)" : tone === "ok" ? "var(--success)" : "var(--text-3)";
  return <div style={{ color, fontSize: "0.9rem" }}>{children}</div>;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.message} (HTTP ${error.status})`;
  return error instanceof Error ? error.message : "Request failed.";
}

function Muted({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return <div style={{ padding: "1rem", color: tone === "error" ? "var(--danger)" : "var(--text-subtle)" }}>{children}</div>;
}
