/**
 * Returns Analysis page (spec Tab 2): the dense daily-return WebGL scatter
 * (`ReturnsScatter`, lazy-loaded so Plotly's bundle stays code-split).
 *
 * Scenario visibility is driven by the chart legend (single-click toggles a
 * scenario, double-click isolates one), so there's no separate picker. The full
 * payload is fetched once.
 */

import { lazy, Suspense, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { useReturns } from "../api/hooks";

const ReturnsScatter = lazy(() => import("../components/charts/ReturnsScatter"));

export function ReturnsPage() {
  const returns = useReturns();

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Returns Analysis</h2>
      <p style={{ color: "#666", marginTop: "0.25rem" }}>
        Daily returns by scenario, rendered with a WebGL scatter for density. Click a legend entry to
        toggle a scenario; double-click to isolate one.
      </p>

      {returns.isLoading ? (
        <Status>Loading returns…</Status>
      ) : returns.isError ? (
        <Status tone="error">{errorMessage(returns.error)}</Status>
      ) : (
        <Suspense fallback={<Status>Loading chart…</Status>}>
          <ReturnsScatter series={returns.data?.series ?? []} />
        </Suspense>
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
