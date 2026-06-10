/**
 * Returns Analysis page (spec Tab 2, Phase 2): the dense daily-return scatter.
 * The Plotly WebGL chart (`ReturnsScatter`) is `React.lazy`-loaded so Plotly's
 * heavy bundle only ships when this tab is opened (§7.1).
 *
 * Perf: like NAV comparison, the full returns payload is fetched ONCE and the
 * `ScenarioSelect` filters which scenarios plot client-side -- toggling never
 * refetches.
 */

import { lazy, Suspense, useMemo, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { useReturns, useScenarios } from "../api/hooks";
import { ScenarioSelect } from "../components/ScenarioSelect";

const ReturnsScatter = lazy(() => import("../components/charts/ReturnsScatter"));

export function ReturnsPage() {
  const scenariosQuery = useScenarios();
  const allScenarios = scenariosQuery.data?.scenarios ?? [];

  const returns = useReturns();

  const [selected, setSelected] = useState<string[] | null>(null);
  const effective = selected ?? allScenarios;

  const shownSeries = useMemo(() => {
    const shownIds = new Set(effective);
    return (returns.data?.series ?? []).filter((s) => shownIds.has(s.scenario_id));
  }, [returns.data, effective]);

  const loading = returns.isLoading || scenariosQuery.isLoading;
  const noneSelected = selected !== null && selected.length === 0;

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Returns Analysis</h2>
      <p style={{ color: "#666", marginTop: "0.25rem" }}>
        Daily returns by scenario, rendered with a WebGL scatter for density.
      </p>

      {allScenarios.length > 0 && (
        <ScenarioSelect scenarios={allScenarios} selected={effective} onChange={setSelected} />
      )}

      {loading ? (
        <Status>Loading returns…</Status>
      ) : returns.isError ? (
        <Status tone="error">{errorMessage(returns.error)}</Status>
      ) : noneSelected ? (
        <Status>Select at least one scenario.</Status>
      ) : (
        <Suspense fallback={<Status>Loading chart…</Status>}>
          <ReturnsScatter series={shownSeries} />
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
