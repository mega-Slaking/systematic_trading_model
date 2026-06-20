/**
 * Volatility Features page (spec Tab 5, Phases 1–6).
 *
 * One diagnostic chart driven by the unified `/chart` endpoint across five views
 * (annualised volatility | historical percentile | 20D/60D ratio | volatility
 * change | estimator dispersion), with optional confirmed-state shading and
 * cooldown-gated transition markers. A state/context card (level, direction,
 * diagnostic state, estimator agreement, price/vol context), an estimator
 * comparison panel, an all-asset confirmed-state table, and the raw latest-values
 * table round it out. Reference estimator + historical window are selectable.
 */

import { lazy, Suspense, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { InfoTooltip } from "../components/InfoTooltip";
import { StatCard, StatGrid } from "../components/StatCard";
import { useUrlState } from "../hooks/useUrlState";
import {
  // useAssetSignalSnapshot, // used by the commented-out Strategy signal snapshot section
  useCrossAssetRatioSeries,
  useCrossAssetVolatility,
  useEstimateStability,
  useEstimatorAgreement,
  useSignalOutcomeConditions,
  useSignalOutcomeDistribution,
  useSignalOutcomes,
  useVolatilityChart,
  useVolatilityContext,
  useVolatilityLatest,
  useVolatilityStateTable,
} from "../api/hooks";
import type {
  AssetRiskRankRow,
  // AssetVolatilitySnapshotResponse, // used by the commented-out Strategy signal snapshot section
  CrossAssetRatioRow,
  EstimateStabilityResponse,
  EstimatorAgreementResponse,
  EstimatorComparisonRow,
  NamedSeries,
  SignalOutcomeDistributionResponse,
  SignalOutcomeResponse,
  SignalOutcomeRow,
  VolatilityContextResponse,
  VolatilityStateRow,
  VolLatestRow,
} from "../api/types";
import { DataTable, type Column } from "../components/tables/DataTable";
import { formatPercent, formatRatio } from "../lib/format";
import { useTheme } from "../theme/ThemeContext";
import { volStateBandColor } from "../theme/regimeColors";

const PlotlyLineChart = lazy(() => import("../components/charts/PlotlyLineChart"));
const OutcomeBoxplot = lazy(() => import("../components/charts/OutcomeBoxplot"));

const VOL_METHODS: Record<string, string> = {
  rolling_20: "Rolling 20d",
  rolling_60: "Rolling 60d",
  ewma_94: "EWMA λ=0.94",
  ewma_97: "EWMA λ=0.97",
  garch: "GARCH(1,1)",
};

const WINDOWS = ["3Y", "5Y", "10Y", "Full"] as const;
// Fallback forward-outcome horizons; the server is the source of truth (response.horizons).
const DEFAULT_HORIZONS = ["1M", "3M", "6M"];
const METHOD_KEYS = Object.keys(VOL_METHODS);
type View = "volatility" | "percentile" | "ratio" | "change" | "dispersion" | "vov";

const CHART_LABELS: Record<View, string> = {
  volatility: "Annualized volatility",
  percentile: "Historical percentile",
  ratio: "20D / 60D ratio",
  change: "Relative volatility change",
  dispersion: "Estimator dispersion (relative)",
  vov: "Estimate stability (vol-of-vol percentile)",
};

const VIEW_KEYS = Object.keys(CHART_LABELS) as View[];

/** Format a decimal annualised-vol spread as percentage points, e.g. 0.0124 -> "1.24 pp". */
function formatPP(value: number | null | undefined, digits = 2): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)} pp`;
}

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
  const { mode } = useTheme();
  const latest = useVolatilityLatest();
  const tickers = (latest.data?.rows ?? []).map((r) => r.ticker);

  // Selections are URL-synced (refresh-safe + shareable). An out-of-range ticker
  // falls back below once the ticker list loads; window/view validate against
  // their fixed option sets.
  const [ticker, setTicker] = useUrlState<string>("volTicker", "");
  const activeTicker = (ticker && tickers.includes(ticker))
    ? ticker
    : (tickers.includes("TLT") ? "TLT" : tickers[0]) || "";

  // Per-ticker available estimators come from the latest-values row (non-null methods).
  const latestRow = (latest.data?.rows ?? []).find((r) => r.ticker === activeTicker);
  const available = latestRow
    ? METHOD_KEYS.filter((m) => (latestRow as Record<string, unknown>)[m] != null)
    : METHOD_KEYS;

  const [view, setView] = useUrlState<View>("volView", "volatility", { allowed: VIEW_KEYS });
  const [windowKey, setWindowKey] = useUrlState<string>("volWindow", "5Y", { allowed: WINDOWS });
  const [refEstimator, setRefEstimator] = useUrlState<string>("volEstimator", "rolling_20");
  const activeEstimator = available.includes(refEstimator)
    ? refEstimator
    : available.includes("rolling_20")
      ? "rolling_20"
      : available[0] ?? "rolling_20";

  const ctx = useVolatilityContext(activeTicker || undefined, activeEstimator, windowKey);
  const chart = useVolatilityChart(activeTicker || undefined, activeEstimator, windowKey, view);
  const stateTable = useVolatilityStateTable(activeEstimator, windowKey);
  const agreement = useEstimatorAgreement(activeTicker || undefined, windowKey);
  const stability = useEstimateStability(activeTicker || undefined, activeEstimator, windowKey);
  const crossAsset = useCrossAssetVolatility(activeEstimator, windowKey);

  const [ratioPair, setRatioPair] = useState<string>("");
  const [ratioView, setRatioView] = useState<"raw" | "percentile">("raw");
  const pairLabels = (crossAsset.data?.ratios ?? []).map((r) => r.pair);
  const activePairLabel = ratioPair || pairLabels[0] || "";
  const ratioSeries = useCrossAssetRatioSeries(
    activePairLabel ? activePairLabel.replace(/\s+/g, "") : undefined,
    activeEstimator,
    windowKey,
    ratioView,
  );

  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [showShading, setShowShading] = useState(true);
  const [showMarkers, setShowMarkers] = useState(false);

  // Phase 10: passive strategy-integration snapshot (as-of defaults to latest).
  // Section removed for now — kept commented for easy restore (see SnapshotPanel below).
  // const [snapshotAsOf, setSnapshotAsOf] = useState<string>("");
  // const snapshot = useAssetSignalSnapshot(
  //   activeTicker || undefined,
  //   activeEstimator,
  //   windowKey,
  //   snapshotAsOf || undefined,
  // );

  // Phase 9: historical signal outcomes (non-overlapping by default).
  const [outcomeSampling, setOutcomeSampling] = useState<"non_overlapping" | "all">("non_overlapping");
  const [outcomeHorizon, setOutcomeHorizon] = useState<string>("1M");
  const [outcomeState, setOutcomeState] = useState<string>("");
  const [outcomeStart, setOutcomeStart] = useState<string>("");
  const [outcomeEnd, setOutcomeEnd] = useState<string>("");
  const outcomes = useSignalOutcomes(
    activeTicker || undefined,
    activeEstimator,
    windowKey,
    outcomeSampling,
    outcomeStart || undefined,
    outcomeEnd || undefined,
  );
  const conditions = useSignalOutcomeConditions(
    activeTicker || undefined,
    activeEstimator,
    windowKey,
    outcomeSampling,
    outcomeStart || undefined,
    outcomeEnd || undefined,
  );
  // Clamp the selected horizon to what the server actually returned, and feed the
  // SAME value to the distribution query so the box plot's data and its header label
  // can never disagree (the tabs only ever set a valid horizon today, but this keeps
  // them coupled if the horizon set ever changes).
  const outcomeHorizons = outcomes.data?.horizons ?? DEFAULT_HORIZONS;
  const activeOutcomeHorizon = outcomeHorizons.includes(outcomeHorizon)
    ? outcomeHorizon
    : outcomeHorizons[0] ?? "1M";
  const distribution = useSignalOutcomeDistribution(
    activeTicker || undefined,
    activeEstimator,
    windowKey,
    activeOutcomeHorizon,
    outcomeSampling,
    outcomeStart || undefined,
    outcomeEnd || undefined,
  );

  function toggleMethod(method: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(method)) next.delete(method);
      else next.add(method);
      return next;
    });
  }

  function renderChart() {
    if (chart.isLoading) return <Muted>Loading chart…</Muted>;
    if (chart.isError) return <Muted tone="error">{errorMessage(chart.error)}</Muted>;
    const data = chart.data;
    if (!data || data.series.length === 0) return <Muted>Insufficient history for this view.</Muted>;

    // VolatilitySeries -> NamedSeries; the volatility view's estimator curves are toggleable.
    let series: NamedSeries[] = data.series.map((s) => ({
      name: s.name, points: s.points, meta: { method: s.method },
    }));
    if (view === "volatility") {
      series = series.filter((s) => !hidden.has((s.meta?.["method"] as string | null) ?? s.name));
    }

    const bands = showShading
      ? data.state_ranges
          .map((r) => ({ start: r.start, end: r.end, color: volStateBandColor(r.state, mode) }))
          .filter((b): b is { start: string; end: string; color: string } => b.color !== null)
      : undefined;
    const markers = showMarkers ? data.transitions.map((t) => ({ date: t.date })) : undefined;

    return (
      <>
        <Suspense fallback={<Muted>Loading chart…</Muted>}>
          <PlotlyLineChart
            series={series}
            yLabel={CHART_LABELS[view]}
            yTickFormat={data.unit === "ratio" ? ".2f" : ".0%"}
            height={460}
            referenceLines={data.reference_lines.map((value) => ({ value }))}
            bands={bands}
            markers={markers}
          />
        </Suspense>
        {view === "ratio" ? <RatioMethodologyNote /> : null}
      </>
    );
  }

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Volatility Features</h2>
      <p style={{ color: "var(--text-muted)", marginTop: "0.25rem" }}>
        Point-in-time annualized volatility per asset (lagged one day — no lookahead).
      </p>

      {/* --- controls: asset, reference estimator, window, view --- */}
      <div style={{ display: "flex", gap: "1.25rem", alignItems: "center", flexWrap: "wrap", marginBottom: "1rem" }}>
        <Control label="Asset">
          <select value={activeTicker} onChange={(e) => setTicker(e.target.value)} style={selectStyle}>
            {tickers.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </Control>
        <Control label="Reference">
          <select value={activeEstimator} onChange={(e) => setRefEstimator(e.target.value)} style={selectStyle}>
            {(available.length ? available : Object.keys(VOL_METHODS)).map((m) => (
              <option key={m} value={m}>{VOL_METHODS[m] ?? m}</option>
            ))}
          </select>
        </Control>
        <Control label="History">
          <select value={windowKey} onChange={(e) => setWindowKey(e.target.value)} style={selectStyle}>
            {WINDOWS.map((w) => (
              <option key={w} value={w}>{w}</option>
            ))}
          </select>
        </Control>
        <Control label="View">
          <div style={{ display: "inline-flex", borderRadius: 6, overflow: "hidden", border: "1px solid var(--border-strong)" }}>
            <ViewTab active={view === "volatility"} onClick={() => setView("volatility")}>Annualised volatility</ViewTab>
            <ViewTab active={view === "percentile"} onClick={() => setView("percentile")}>Historical percentile</ViewTab>
            <ViewTab active={view === "ratio"} onClick={() => setView("ratio")}>20D / 60D ratio</ViewTab>
            <ViewTab active={view === "change"} onClick={() => setView("change")}>Change in volatility</ViewTab>
            <ViewTab active={view === "dispersion"} onClick={() => setView("dispersion")}>Estimator dispersion</ViewTab>
            <ViewTab active={view === "vov"} onClick={() => setView("vov")}>Volatility of volatility</ViewTab>
          </div>
        </Control>
        <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem", color: "var(--text-3)" }}>
          <input type="checkbox" checked={showShading} onChange={(e) => setShowShading(e.target.checked)} />
          State shading
        </label>
        <label style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", fontSize: "0.85rem", color: "var(--text-3)" }}>
          <input type="checkbox" checked={showMarkers} onChange={(e) => setShowMarkers(e.target.checked)} />
          Transition markers
        </label>
      </div>

      {/* --- estimator toggles (annualised view only) --- */}
      {view === "volatility" && (
        <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", marginBottom: "1rem" }}>
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
      )}

      <section style={{ marginBottom: "1.5rem" }}>
        {renderChart()}
        {showShading ? <StateLegend /> : null}
      </section>

      {/* --- volatility state + context card (Phases 1–4) — below the chart, which is the centrepiece --- */}
      <ContextCard
        ticker={activeTicker}
        estimator={activeEstimator}
        window={windowKey}
        data={ctx.data}
        isLoading={ctx.isLoading}
        agreement={agreement.data}
        stabilityData={stability.data}
        stabilityLoading={stability.isLoading}
      />

      <h3 style={{ marginBottom: "0.25rem" }}>Estimator comparison</h3>
      <p style={{ color: "var(--text-subtle)", fontSize: "0.8rem", marginTop: 0, marginBottom: "0.5rem" }}>
        Each estimator's latest reading vs the cross-estimator median ({windowKey} percentile).
      </p>
      {agreement.isLoading ? (
        <Muted>Loading…</Muted>
      ) : agreement.isError ? (
        <Muted tone="error">{errorMessage(agreement.error)}</Muted>
      ) : (
        <DataTable columns={ESTIMATOR_COLUMNS} rows={agreement.data?.rows ?? []} />
      )}

      <h3 style={{ marginBottom: "0.25rem", marginTop: "1.5rem" }}>Volatility states</h3>
      <p style={{ color: "var(--text-subtle)", fontSize: "0.8rem", marginTop: 0, marginBottom: "0.5rem" }}>
        Confirmed diagnostic state per asset (persistence-debounced; {windowKey} percentile,{" "}
        {VOL_METHODS[activeEstimator] ?? activeEstimator}). Diagnostic only — not a trading signal.
      </p>
      {stateTable.isLoading ? (
        <Muted>Loading…</Muted>
      ) : stateTable.isError ? (
        <Muted tone="error">{errorMessage(stateTable.error)}</Muted>
      ) : (
        <DataTable columns={STATE_COLUMNS} rows={stateTable.data?.rows ?? []} />
      )}

      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "1.5rem", marginBottom: "0.5rem" }}>
        <h3 style={{ margin: 0 }}>Cross-asset risk</h3>
        <InfoTooltip label="About cross-asset risk">
          Relative volatility between assets and each ratio's own history. Monitor only. Ratios like TLT/SHY trend with the duration differential, so a high percentile is a single-path, trend-laden reading — not a tradable risk signal. The ranking is by raw current volatility (TLT ≈ always outranks SHY by duration); the percentile and confirmed state carry the real relative context.
        </InfoTooltip>
      </div>
      {crossAsset.isLoading ? (
        <Muted>Loading…</Muted>
      ) : crossAsset.isError ? (
        <Muted tone="error">{errorMessage(crossAsset.error)}</Muted>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-3)", marginBottom: "0.3rem" }}>Relative-volatility ratios</div>
            <DataTable columns={RATIO_COLUMNS} rows={crossAsset.data?.ratios ?? []} />
          </div>
          <div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-3)", marginBottom: "0.3rem" }}>Risk ranking (raw vol)</div>
            <DataTable columns={RANK_COLUMNS} rows={crossAsset.data?.ranking ?? []} />
          </div>
        </div>
      )}

      {pairLabels.length > 0 && (
        <div style={{ marginTop: "1.25rem" }}>
          <div style={{ display: "flex", gap: "1.25rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.5rem" }}>
            <Control label="Pair">
              <select value={activePairLabel} onChange={(e) => setRatioPair(e.target.value)} style={selectStyle}>
                {pairLabels.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </Control>
            <div style={{ display: "inline-flex", borderRadius: 6, overflow: "hidden", border: "1px solid var(--border-strong)" }}>
              <ViewTab active={ratioView === "raw"} onClick={() => setRatioView("raw")}>Raw ratio</ViewTab>
              <ViewTab active={ratioView === "percentile"} onClick={() => setRatioView("percentile")}>Historical percentile</ViewTab>
            </div>
          </div>
          {ratioSeries.isLoading ? (
            <Muted>Loading…</Muted>
          ) : ratioSeries.isError ? (
            <Muted tone="error">{errorMessage(ratioSeries.error)}</Muted>
          ) : (
            <Suspense fallback={<Muted>Loading chart…</Muted>}>
              <PlotlyLineChart
                series={ratioSeries.data?.series ?? []}
                yLabel={`${activePairLabel} ${ratioView === "percentile" ? "percentile" : "ratio"}`}
                yTickFormat={ratioView === "percentile" ? ".0%" : ".2f"}
                height={380}
                referenceLines={(ratioSeries.data?.reference_lines ?? []).map((value) => ({ value }))}
              />
            </Suspense>
          )}
        </div>
      )}

      <OutcomesSection
        ticker={activeTicker}
        estimator={activeEstimator}
        data={outcomes.data}
        isLoading={outcomes.isLoading}
        isError={outcomes.isError}
        error={outcomes.error}
        conditionsData={conditions.data}
        conditionsLoading={conditions.isLoading}
        conditionsError={conditions.isError}
        distribution={distribution.data}
        distributionLoading={distribution.isLoading}
        distributionError={distribution.isError}
        sampling={outcomeSampling}
        setSampling={setOutcomeSampling}
        horizons={outcomeHorizons}
        activeHorizon={activeOutcomeHorizon}
        setHorizon={setOutcomeHorizon}
        stateFilter={outcomeState}
        setStateFilter={setOutcomeState}
        start={outcomeStart}
        setStart={setOutcomeStart}
        end={outcomeEnd}
        setEnd={setOutcomeEnd}
      />

      {/* Strategy signal snapshot section removed for now — added confusion without clear value.
          The SnapshotPanel component + snapshot hook/state below remain defined for easy restore.
      <SnapshotPanel
        ticker={activeTicker}
        estimator={activeEstimator}
        data={snapshot.data}
        isLoading={snapshot.isLoading}
        isError={snapshot.isError}
        error={snapshot.error}
        asOf={snapshotAsOf}
        setAsOf={setSnapshotAsOf}
      />
      */}

      <h3 style={{ marginBottom: "0.5rem", marginTop: "1.5rem" }}>Latest values</h3>
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

const STATE_COLUMNS: Column<VolatilityStateRow>[] = [
  { key: "ticker", header: "Ticker" },
  {
    key: "confirmed_state",
    header: "State",
    render: (r) => <StateBadge state={r.confirmed_state} />,
    sortValue: (r) => r.confirmed_state,
  },
  {
    key: "percentile_ordinal",
    header: "Percentile",
    align: "right",
    render: (r) => ordinal(r.percentile_ordinal ?? null),
    sortValue: (r) => r.percentile_ordinal ?? null,
  },
  {
    key: "current_volatility",
    header: "Vol",
    align: "right",
    render: (r) => formatPercent(r.current_volatility ?? null),
    sortValue: (r) => r.current_volatility ?? null,
  },
  {
    key: "change_20d",
    header: "20D Δ",
    align: "right",
    render: (r) => formatPercent(r.change_20d ?? null, 1),
    sortValue: (r) => r.change_20d ?? null,
  },
  {
    key: "term_ratio",
    header: "20D/60D",
    align: "right",
    render: (r) => formatRatio(r.term_ratio ?? null),
    sortValue: (r) => r.term_ratio ?? null,
  },
  { key: "term_state", header: "Term" },
  {
    key: "asset_return_20d",
    header: "20D ret",
    align: "right",
    render: (r) => formatPercent(r.asset_return_20d ?? null, 1),
    sortValue: (r) => r.asset_return_20d ?? null,
  },
  { key: "price_volatility_context", header: "Price / Vol" },
  { key: "estimate_stability", header: "Stability" },
  {
    key: "stability_percentile",
    header: "Estab %ile",
    align: "right",
    render: (r) => ordinal(r.stability_percentile != null ? Math.round(r.stability_percentile * 100) : null),
    sortValue: (r) => r.stability_percentile ?? null,
  },
];

const ESTIMATOR_COLUMNS: Column<EstimatorComparisonRow>[] = [
  { key: "estimator", header: "Estimator" },
  {
    key: "current_volatility",
    header: "Current",
    align: "right",
    render: (r) => formatPercent(r.current_volatility ?? null),
    sortValue: (r) => r.current_volatility ?? null,
  },
  {
    key: "historical_percentile_ordinal",
    header: "Percentile",
    align: "right",
    render: (r) => ordinal(r.historical_percentile_ordinal ?? null),
    sortValue: (r) => r.historical_percentile_ordinal ?? null,
  },
  {
    key: "absolute_diff_vs_median",
    header: "Abs vs median",
    align: "right",
    render: (r) => formatPP(r.absolute_diff_vs_median ?? null),
    sortValue: (r) => r.absolute_diff_vs_median ?? null,
  },
  {
    key: "relative_diff_vs_median",
    header: "Rel vs median",
    align: "right",
    render: (r) => formatPercent(r.relative_diff_vs_median ?? null, 1),
    sortValue: (r) => r.relative_diff_vs_median ?? null,
  },
];

const RATIO_COLUMNS: Column<CrossAssetRatioRow>[] = [
  { key: "pair", header: "Pair" },
  {
    key: "current_ratio",
    header: "Ratio",
    align: "right",
    render: (r) => formatRatio(r.current_ratio ?? null),
    sortValue: (r) => r.current_ratio ?? null,
  },
  {
    key: "percentile_ordinal",
    header: "Percentile",
    align: "right",
    render: (r) => ordinal(r.percentile_ordinal ?? null),
    sortValue: (r) => r.percentile_ordinal ?? null,
  },
  { key: "relative_risk_state", header: "Relative risk" },
];

const RANK_COLUMNS: Column<AssetRiskRankRow>[] = [
  { key: "rank", header: "#", align: "right" },
  { key: "ticker", header: "Ticker" },
  {
    key: "current_volatility",
    header: "Vol",
    align: "right",
    render: (r) => formatPercent(r.current_volatility ?? null),
    sortValue: (r) => r.current_volatility ?? null,
  },
  {
    key: "percentile_ordinal",
    header: "Percentile",
    align: "right",
    render: (r) => ordinal(r.percentile_ordinal ?? null),
    sortValue: (r) => r.percentile_ordinal ?? null,
  },
  {
    key: "confirmed_state",
    header: "State",
    render: (r) => <StateBadge state={r.confirmed_state} />,
    sortValue: (r) => r.confirmed_state,
  },
];

const selectStyle: React.CSSProperties = {
  padding: "0.35rem 0.5rem", borderRadius: 6, border: "1px solid var(--border-strong)",
};

function Control({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
      <span style={{ color: "var(--text-3)", fontSize: "0.9rem" }}>{label}:</span>
      {children}
    </label>
  );
}

function ViewTab({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: "0.35rem 0.7rem", fontSize: "0.85rem", cursor: "pointer", border: "none",
        background: active ? "var(--accent)" : "var(--surface)",
        color: active ? "var(--accent-contrast, #fff)" : "var(--text-muted)",
      }}
    >
      {children}
    </button>
  );
}

/** The Phase 3 volatility-state card: confirmed state headline + explanation + inputs. */
function ContextCard({
  ticker,
  estimator,
  window,
  data,
  isLoading,
  agreement,
  stabilityData,
  stabilityLoading,
}: {
  ticker: string;
  estimator: string;
  window: string;
  data: VolatilityContextResponse | undefined;
  isLoading: boolean;
  agreement: EstimatorAgreementResponse | undefined;
  stabilityData: EstimateStabilityResponse | undefined;
  stabilityLoading: boolean;
}) {
  const insufficient = data?.insufficient_history ?? false;
  const level = data?.volatility_level ?? "—";
  const confirmed = data?.confirmed_state ?? "—";
  const instantaneous = data?.instantaneous_state;

  return (
    <section style={{ marginBottom: "1.25rem" }}>
      {/* headline: confirmed state + as-of */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap", marginBottom: "0.6rem" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
          <span style={{ fontSize: "0.75rem", color: "var(--text-subtle)" }}>
            {ticker} · {VOL_METHODS[estimator] ?? estimator} — Volatility State
          </span>
          {isLoading ? (
            <span style={{ color: "var(--text-subtle)" }}>Loading…</span>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
              <StateBadge state={confirmed} large />
              {instantaneous && instantaneous !== confirmed ? (
                <span title="Instantaneous (un-debounced) state" style={{ fontSize: "0.78rem", color: "var(--text-subtle)" }}>
                  now: {instantaneous}
                </span>
              ) : null}
            </div>
          )}
        </div>
        <div style={{ textAlign: "right", fontSize: "0.75rem", color: "var(--text-subtle)" }}>
          As of {data?.as_of_date ?? "—"}
          {data?.information_through_date ? <><br />data through {data.information_through_date}</> : null}
        </div>
      </div>

      {!isLoading && data?.state_explanation ? (
        <p style={{ margin: "0 0 0.75rem", fontSize: "0.85rem", color: "var(--text-muted)", maxWidth: 820 }}>
          {data.state_explanation}
        </p>
      ) : null}

      {isLoading ? null : insufficient ? (
        <span style={{ color: "var(--text-muted)" }}>Insufficient history</span>
      ) : (
        <StatGrid minColWidth={160} gap="0.75rem">
          <StatCard label="Current" value={formatPercent(data?.current_volatility ?? null)} />
          <StatCard label={`${data?.historical_window ?? ""} percentile`} value={ordinal(data?.percentile_ordinal ?? null)} />
          <StatCard label="Level">
            <span style={{ ...levelStyle(level), display: "inline-block", padding: "0.1rem 0.5rem", borderRadius: 999, fontSize: "0.9rem", fontWeight: 600 }}>{level}</span>
          </StatCard>
          <StatCard label="20D direction" value={data?.direction ?? "—"} />
          <StatCard label="20D change" value={formatPercent(data?.change_20d ?? null, 1)} />
          <StatCard label="20D / 60D" value={formatRatio(data?.term_ratio ?? null)} />
          <StatCard label="Term state" value={data?.term_state ?? "—"} />
          <StatCard label="Agreement" value={data?.estimator_agreement ?? "—"} />
          <StatCard label="Absolute spread" value={formatPP(data?.absolute_spread ?? null)} />
          <StatCard label="Relative dispersion" value={formatPercent(data?.relative_dispersion ?? null, 1)} />
          <StatCard label="Highest estimator" value={agreement?.highest_estimator ?? "—"} />
          <StatCard label="Lowest estimator" value={agreement?.lowest_estimator ?? "—"} />
          <StatCard label="Price / Vol context" value={data?.price_volatility_context ?? "—"} />
          <StatCard label="20D asset return" value={formatPercent(data?.asset_return_20d ?? null, 1)} />
          <StatCard label="20D vol change" value={formatPercent(data?.vol_change_20d ?? null, 1)} />
          <StatCard
            label={`${window} stability %ile`}
            value={stabilityLoading ? "…" : ordinal(stabilityData?.percentile_ordinal ?? null)}
            info="20D std dev of daily changes in annualised volatility, ranked vs history. High percentile means the risk estimate is changing quickly and position sizes derived from it would be less stable. Diagnostic only — no sizing change is implied."
          />
          <StatCard
            label="Stability status"
            info="Derived from the vol-of-vol percentile. Diagnostic only — no sizing change is implied."
          >
            {(() => {
              const status = stabilityLoading ? "…" : (stabilityData?.estimate_stability ?? "—");
              const s = stabilityStyle(status);
              return (
                <span style={{ ...s, display: "inline-block", padding: "0.1rem 0.5rem", borderRadius: 999, fontSize: "0.9rem", fontWeight: 600 }}>
                  {status}
                </span>
              );
            })()}
          </StatCard>
        </StatGrid>
      )}
    </section>
  );
}

/** Badge colours for the stability status (data-meaning, constant across themes). */
function stabilityStyle(status: string): { background: string; color: string } {
  if (status === "Unstable" || status === "Extreme instability")
    return { background: "var(--danger-bg, rgba(220,38,38,0.12))", color: "var(--danger)" };
  if (status === "Changing")
    return { background: "rgba(217,119,6,0.16)", color: "#b45309" };
  if (status === "Stable")
    return { background: "var(--accent-bg)", color: "var(--accent)" };
  return { background: "transparent", color: "var(--text-muted)" };
}

// Stat and LabeledBadge are only used by the commented-out Strategy signal snapshot
// section below — kept commented for easy restore alongside it.
/*
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
      <span style={{ fontSize: "0.72rem", color: "var(--text-subtle)" }}>{label}</span>
      <span style={{ fontSize: "1.05rem", fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function LabeledBadge({ label, text, style }: { label: string; text: string; style: { background: string; color: string } }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
      <span style={{ fontSize: "0.72rem", color: "var(--text-subtle)" }}>{label}</span>
      <span style={{
        padding: "0.1rem 0.5rem", borderRadius: 999, fontSize: "0.85rem", fontWeight: 600,
        background: style.background, color: style.color, width: "fit-content",
      }}>
        {text}
      </span>
    </div>
  );
}
*/

/** Coloured pill for a diagnostic state (shared by the card headline and the table). */
function StateBadge({ state, large = false }: { state: string; large?: boolean }) {
  const s = stateStyle(state);
  return (
    <span style={{
      padding: large ? "0.2rem 0.7rem" : "0.1rem 0.5rem", borderRadius: 999,
      fontSize: large ? "1.05rem" : "0.82rem", fontWeight: large ? 700 : 600,
      background: s.background, color: s.color, whiteSpace: "nowrap",
    }}>
      {state}
    </span>
  );
}

function levelStyle(level: string): { background: string; color: string } {
  if (level === "High" || level === "Extreme")
    return { background: "var(--danger-bg, rgba(220,38,38,0.12))", color: "var(--danger)" };
  if (level === "Low" || level === "Normal" || level === "Elevated")
    return { background: "var(--accent-bg)", color: "var(--accent)" };
  return { background: "transparent", color: "var(--text-muted)" };
}

/** Colour key for the chart's confirmed-state shading. */
function StateLegend() {
  const { mode } = useTheme();
  const states = ["Calm", "Early Expansion", "Stress Expansion", "Persistent Stress", "Normalisation", "Shock", "Unknown"];
  return (
    <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center", marginTop: "0.6rem", fontSize: "0.78rem", color: "var(--text-subtle)" }}>
      <span style={{ fontWeight: 600 }}>Confirmed state:</span>
      {states.map((s) => {
        const fill = volStateBandColor(s, mode);
        return (
          <span key={s} style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
            <span style={{
              width: 14, height: 14, borderRadius: 3,
              background: fill ?? "transparent",
              border: fill ? "1px solid var(--border-strong)" : "1px dashed var(--border-strong)",
            }} />
            {s}
          </span>
        );
      })}
      <span style={{ fontStyle: "italic" }}>Calm is unshaded (baseline). Markers = regime change.</span>
    </div>
  );
}

/** Data-meaning colours for diagnostic states (constant across themes, like the chart bands). */
function stateStyle(state: string): { background: string; color: string } {
  switch (state) {
    case "Shock":
    case "Stress Expansion":
    case "Persistent Stress":
      return { background: "var(--danger-bg, rgba(220,38,38,0.12))", color: "var(--danger)" };
    case "Early Expansion":
      return { background: "rgba(217,119,6,0.16)", color: "#b45309" };
    case "Calm":
    case "Normalisation":
      return { background: "var(--accent-bg)", color: "var(--accent)" };
    default: // Unknown
      return { background: "transparent", color: "var(--text-muted)" };
  }
}

/** 24 -> "24th". */
function ordinal(n: number | null): string {
  if (n == null) return "—";
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`;
}

/** Methodology caveat for the overlapping-window 20D/60D ratio (spec Phase 2). */
function RatioMethodologyNote() {
  return (
    <p style={{ marginTop: "0.5rem", fontSize: "0.78rem", color: "var(--text-subtle)", maxWidth: 760 }}>
      Note: rolling 20D and 60D volatility use <strong>overlapping</strong> return windows, so this
      ratio is mechanically mean-reverting toward 1 and the two series are correlated by construction.
      The 0.85 / 1.15 bands are descriptive, not statistically derived — read it as “is short-term
      volatility pulling away from its own 60-day baseline?”, not as a ratio of independent quantities.
    </p>
  );
}

/** Sample-quality badge colours (data-meaning, constant across themes). */
function sampleQualityStyle(quality: string): { background: string; color: string } {
  if (quality === "Insufficient sample")
    return { background: "var(--danger-bg, rgba(220,38,38,0.12))", color: "var(--danger)" };
  if (quality === "Anecdotal")
    return { background: "rgba(217,119,6,0.16)", color: "#b45309" };
  if (quality === "Low sample")
    return { background: "rgba(217,119,6,0.10)", color: "#b45309" };
  return { background: "var(--accent-bg)", color: "var(--accent)" }; // adequate sample
}

const OUTCOME_COLUMNS: Column<SignalOutcomeRow>[] = [
  {
    key: "state",
    header: "State",
    render: (r) => <StateBadge state={r.state} />,
    sortValue: (r) => r.state,
  },
  {
    key: "effective_observations",
    header: "Independent obs",
    align: "right",
    // The effective independent count is the headline — show it prominently bold.
    render: (r) => <strong>{r.effective_observations}</strong>,
    sortValue: (r) => r.effective_observations,
  },
  {
    key: "sample_quality",
    header: "Sample quality",
    render: (r) =>
      r.sample_quality ? (
        <span
          style={{
            padding: "0.05rem 0.45rem", borderRadius: 999, fontSize: "0.78rem", fontWeight: 600,
            ...sampleQualityStyle(r.sample_quality),
          }}
        >
          {r.sample_quality}
        </span>
      ) : (
        <span style={{ color: "var(--text-subtle)", fontSize: "0.8rem" }}>Adequate</span>
      ),
    sortValue: (r) => r.sample_quality,
  },
  {
    key: "mean_return",
    header: "Mean",
    align: "right",
    render: (r) => formatPercent(r.mean_return ?? null, 2),
    sortValue: (r) => r.mean_return ?? null,
  },
  {
    key: "median_return",
    header: "Median",
    align: "right",
    render: (r) => formatPercent(r.median_return ?? null, 2),
    sortValue: (r) => r.median_return ?? null,
  },
  {
    key: "hit_rate",
    header: "Hit rate",
    align: "right",
    render: (r) => formatPercent(r.hit_rate ?? null, 0),
    sortValue: (r) => r.hit_rate ?? null,
  },
  {
    key: "worst_return",
    header: "Worst",
    align: "right",
    render: (r) => formatPercent(r.worst_return ?? null, 1),
    sortValue: (r) => r.worst_return ?? null,
  },
  {
    key: "best_return",
    header: "Best",
    align: "right",
    render: (r) => formatPercent(r.best_return ?? null, 1),
    sortValue: (r) => r.best_return ?? null,
  },
  {
    key: "forward_max_drawdown",
    header: "Fwd max DD",
    align: "right",
    render: (r) => formatPercent(r.forward_max_drawdown ?? null, 1),
    sortValue: (r) => r.forward_max_drawdown ?? null,
  },
];

/** Combined-condition rows reuse the outcome stat columns but show the condition label as text. */
const CONDITION_COLUMNS: Column<SignalOutcomeRow>[] = [
  {
    key: "state",
    header: "Condition",
    render: (r) => <span style={{ fontWeight: 600 }}>{r.state}</span>,
    sortValue: (r) => r.state,
  },
  ...OUTCOME_COLUMNS.slice(1),
];

/** Phase 9 "Historical Signal Outcomes" section: forward stats by state, gated + disclaimed. */
function OutcomesSection({
  ticker,
  estimator,
  data,
  isLoading,
  isError,
  error,
  conditionsData,
  conditionsLoading,
  conditionsError,
  distribution,
  distributionLoading,
  distributionError,
  sampling,
  setSampling,
  horizons,
  activeHorizon,
  setHorizon,
  stateFilter,
  setStateFilter,
  start,
  setStart,
  end,
  setEnd,
}: {
  ticker: string;
  estimator: string;
  data: SignalOutcomeResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  conditionsData: SignalOutcomeResponse | undefined;
  conditionsLoading: boolean;
  conditionsError: boolean;
  distribution: SignalOutcomeDistributionResponse | undefined;
  distributionLoading: boolean;
  distributionError: boolean;
  sampling: "non_overlapping" | "all";
  setSampling: (s: "non_overlapping" | "all") => void;
  horizons: string[];
  activeHorizon: string;
  setHorizon: (h: string) => void;
  stateFilter: string;
  setStateFilter: (s: string) => void;
  start: string;
  setStart: (s: string) => void;
  end: string;
  setEnd: (s: string) => void;
}) {
  const allRows = data?.rows ?? [];
  const states = Array.from(new Set(allRows.map((r) => r.state)));
  // Filter to the chosen horizon and (optionally) a single state.
  const rows = allRows
    .filter((r) => r.horizon === activeHorizon)
    .filter((r) => (stateFilter ? r.state === stateFilter : true));
  const totalIndependent = rows.reduce((acc, r) => acc + r.effective_observations, 0);

  return (
    <section style={{ marginTop: "2rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.6rem" }}>
        <h3 style={{ margin: 0 }}>Historical signal outcomes</h3>
        <InfoTooltip label="About historical signal outcomes">
          What forward returns followed each confirmed diagnostic state for {ticker || "—"} ({VOL_METHODS[estimator] ?? estimator}). Forward returns are measured from unlagged prices strictly after the signal date; the state is the already-lagged, point-in-time reading. The independent observation count is the headline — non-overlapping windows by default.
        </InfoTooltip>
      </div>

      {/* controls: state filter, horizon, date range, sampling */}
      <div style={{ display: "flex", gap: "1.25rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.75rem" }}>
        <Control label="State">
          <select value={stateFilter} onChange={(e) => setStateFilter(e.target.value)} style={selectStyle}>
            <option value="">All states</option>
            {states.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </Control>
        <Control label="Horizon">
          <div style={{ display: "inline-flex", borderRadius: 6, overflow: "hidden", border: "1px solid var(--border-strong)" }}>
            {horizons.map((h) => (
              <ViewTab key={h} active={activeHorizon === h} onClick={() => setHorizon(h)}>{h}</ViewTab>
            ))}
          </div>
        </Control>
        <Control label="From">
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} style={selectStyle} />
        </Control>
        <Control label="To">
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} style={selectStyle} />
        </Control>
        <Control label="Sampling">
          <div style={{ display: "inline-flex", borderRadius: 6, overflow: "hidden", border: "1px solid var(--border-strong)" }}>
            <ViewTab active={sampling === "non_overlapping"} onClick={() => setSampling("non_overlapping")}>
              Non-overlapping
            </ViewTab>
            <ViewTab active={sampling === "all"} onClick={() => setSampling("all")}>All observations</ViewTab>
          </div>
        </Control>
      </div>

      {sampling === "all" ? (
        <p style={{ margin: "0 0 0.6rem", fontSize: "0.78rem", color: "#b45309", maxWidth: 880 }}>
          <strong>All observations:</strong> overlapping daily forward windows overstate the independent evidence —
          these counts are not statistically independent. Non-overlapping sampling is the honest default.
        </p>
      ) : null}

      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.4rem" }}>
        <span style={{ fontSize: "0.85rem", color: "var(--text-3)" }}>
          Independent observations shown ({activeHorizon}): <strong>{totalIndependent}</strong>
        </span>
        <InfoTooltip label="How to read these outcomes">
          {data?.disclaimer ??
            "Outcomes describe what historically followed similar diagnostic states in this single sample. They do not establish causality and do not guarantee future performance."}{" "}
          Non-overlapping sampling is the default because overlapping daily forward windows overstate the
          independent evidence. Stats are suppressed below the minimum-sample gates: under 5 independent
          observations show no stats (Insufficient sample); 5–9 show count / median / worst / best only
          (Anecdotal); 10–19 show descriptive stats (Low sample); 20+ show the full summary.
        </InfoTooltip>
      </div>

      {isLoading ? (
        <Muted>Loading…</Muted>
      ) : isError ? (
        <Muted tone="error">{errorMessage(error)}</Muted>
      ) : rows.length === 0 ? (
        <Muted>No states with observations for this horizon / date range.</Muted>
      ) : (
        <DataTable columns={OUTCOME_COLUMNS} rows={rows} />
      )}

      {/* Forward-return distribution by state (same sampled observations as the table above). */}
      {distributionLoading ? (
        <Muted>Loading distribution…</Muted>
      ) : distributionError ? (
        <Muted tone="error">Failed to load the forward-return distribution.</Muted>
      ) : distribution && distribution.distributions.length > 0 ? (
        <div style={{ marginTop: "1rem" }}>
          <div style={{ fontSize: "0.8rem", color: "var(--text-3)", marginBottom: "0.3rem" }}>
            Forward-return distribution by state ({activeHorizon}) — box = IQR, line = median, points = outliers.
          </div>
          <Suspense fallback={<Muted>Loading chart…</Muted>}>
            <OutcomeBoxplot distributions={distribution.distributions} horizon={activeHorizon} height={360} />
          </Suspense>
        </div>
      ) : null}

      {/* Combined-condition signals (added incrementally on top of the six diagnostic states). */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "1.5rem", marginBottom: "0.5rem" }}>
        <h4 style={{ margin: 0 }}>Combined-condition signals</h4>
        <InfoTooltip label="About combined-condition signals">
          Forward outcomes after specific point-in-time conditions (e.g. volatility rising while price falls), at the {activeHorizon} horizon. A single day may satisfy several conditions, so these are analysed independently — not as one combined state. Same minimum-sample gates as above.
        </InfoTooltip>
      </div>
      {conditionsLoading ? (
        <Muted>Loading…</Muted>
      ) : conditionsError ? (
        <Muted tone="error">Failed to load combined-condition signals.</Muted>
      ) : (
        (() => {
          const condRows = (conditionsData?.rows ?? []).filter((r) => r.horizon === activeHorizon);
          return condRows.length === 0 ? (
            <Muted>No combined-condition signals for this horizon / date range.</Muted>
          ) : (
            <DataTable columns={CONDITION_COLUMNS} rows={condRows} />
          );
        })()
      )}
    </section>
  );
}

// ===== Strategy signal snapshot — REMOVED FROM UI for now (kept for easy restore) =====
// Phase 10 "Strategy signal snapshot" panel: the passive, typed, point-in-time
// snapshot a strategy/risk layer could consume — with full reproducibility
// metadata and both information-time dates. Explicitly NOT wired to allocation.
/*
function SnapshotPanel({
  ticker,
  estimator,
  data,
  isLoading,
  isError,
  error,
  asOf,
  setAsOf,
}: {
  ticker: string;
  estimator: string;
  data: AssetVolatilitySnapshotResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  asOf: string;
  setAsOf: (s: string) => void;
}) {
  return (
    <section style={{ marginTop: "2rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap", marginBottom: "0.6rem" }}>
        <h3 style={{ margin: 0 }}>Strategy signal snapshot</h3>
        <InfoTooltip label="About strategy signal snapshot">
          The stable, typed, point-in-time snapshot that strategy / risk layers could consume, with full reproducibility metadata. Producing it changes no allocation, sizing, or weight. Point-in-time via the existing as-of path; {ticker || "—"} ({VOL_METHODS[estimator] ?? estimator}).
        </InfoTooltip>
        <span style={{
          padding: "0.1rem 0.5rem", borderRadius: 999, fontSize: "0.72rem", fontWeight: 700,
          background: "rgba(217,119,6,0.16)", color: "#b45309",
        }}>
          Passive — not wired to allocation
        </span>
      </div>

      <div style={{ display: "flex", gap: "1.25rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.75rem" }}>
        <Control label="As of">
          <input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} style={selectStyle} />
        </Control>
        {asOf ? (
          <button
            type="button"
            onClick={() => setAsOf("")}
            style={{ ...selectStyle, cursor: "pointer", background: "var(--surface)" }}
          >
            Latest
          </button>
        ) : (
          <span style={{ fontSize: "0.8rem", color: "var(--text-subtle)" }}>Latest available</span>
        )}
      </div>

      {isLoading ? (
        <Muted>Loading snapshot…</Muted>
      ) : isError ? (
        <Muted tone="error">{errorMessage(error)}</Muted>
      ) : !data ? (
        <Muted>No snapshot.</Muted>
      ) : (
        <div style={{ border: "1px solid var(--border-strong)", borderRadius: 8, padding: "0.9rem 1rem", background: "var(--surface)" }}>
          {/* diagnostic states / features }
          <div style={{ display: "flex", gap: "1.75rem", alignItems: "center", flexWrap: "wrap" }}>
            <LabeledBadge label="Confirmed state" text={data.confirmed_state} style={stateStyle(data.confirmed_state)} />
            <Stat label="Annualised vol" value={formatPercent(data.annualized_volatility ?? null)} />
            <Stat label={`${data.historical_window} percentile`} value={ordinal(data.percentile_ordinal ?? null)} />
            <LabeledBadge label="Level" text={data.volatility_level} style={levelStyle(data.volatility_level)} />
            <Stat label="Direction" value={data.direction} />
            <Stat label="20D / 60D" value={formatRatio(data.short_long_ratio ?? null)} />
            <Stat label="Term state" value={data.term_state} />
            <Stat label="Agreement" value={data.estimator_agreement} />
            <Stat label="Price / Vol" value={data.price_volatility_context} />
            <Stat label="Estimate stability" value={data.estimate_stability} />
          </div>

          {/* reproducibility metadata + information-time dates }
          <div style={{
            display: "flex", gap: "1.5rem", alignItems: "center", flexWrap: "wrap",
            marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border-strong)",
          }}>
            <MetaItem label="As of (t)" value={data.as_of_date ?? "—"} />
            <MetaItem label="Info through (t-1)" value={data.information_through_date ?? "—"} />
            <MetaItem label="Reference" value={data.reference_estimator} />
            <MetaItem label="Window" value={data.historical_window} />
            <MetaItem label="Min history" value={String(data.minimum_history)} />
            <MetaItem label="Confirmation days" value={String(data.confirmation_days)} />
            <MetaItem label="config_key" value={data.config_key || "—"} mono />
            <MetaItem label="state cfg" value={data.state_config_version} mono />
            <MetaItem label="agreement cfg" value={data.agreement_config_version ?? "—"} mono />
            <MetaItem label="stability window" value={data.stability_window ?? "—"} />
          </div>

          {/* Indicative posture + future hooks, side by side so they fill the card width
              instead of wrapping into a narrow column. }
          <div style={{
            marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border-strong)",
            display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "1.5rem",
          }}>
            {/* Indicative posture: what a strategy COULD read from this snapshot — derived from the
                readings above, but explicitly not applied to any weight here. }
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.4rem" }}>
                <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--text-3)" }}>Indicative posture</span>
                <span style={{
                  padding: "0.05rem 0.45rem", borderRadius: 999, fontSize: "0.68rem", fontWeight: 700,
                  background: "rgba(217,119,6,0.16)", color: "#b45309",
                }}>
                  Read-only — not applied
                </span>
              </div>
              <ul style={{ margin: "0", paddingLeft: "1.1rem", fontSize: "0.8rem", color: "var(--text-muted)", lineHeight: 1.55 }}>
                {snapshotActions(data).map((a, i) => (
                  <li key={i} style={{ marginBottom: "0.7rem" }}>{a}</li>
                ))}
              </ul>
            </div>

            {/* Future, intentionally-unimplemented strategy hooks. }
            <div style={{ fontSize: "0.76rem", color: "var(--text-subtle)" }}>
              <span style={{ fontWeight: 600 }}>Documented, intentionally not implemented here</span> — each needs its own reviewed design:
              <ul style={{ margin: "0.3rem 0 0", paddingLeft: "1.1rem", lineHeight: 1.55 }}>
                <li style={{ marginBottom: "0.7rem" }}><strong>Position sizing</strong> — scale toward a target volatility (target_vol ÷ estimated_vol).</li>
                <li style={{ marginBottom: "0.7rem" }}><strong>Risk overlays</strong> — extreme percentile → lower max weight; low agreement → more conservative estimate; unstable estimate → slower weight changes.</li>
                <li><strong>Allocation context</strong> — how this asset's reading fits the wider book.</li>
              </ul>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

// Indicative-only reading of a snapshot: the plain-English actions a strategy/risk
// layer COULD take given these readings. Purely descriptive — nothing changes a weight.
function snapshotActions(data: AssetVolatilitySnapshotResponse): string[] {
  const out: string[] = [];

  const vol = data.annualized_volatility;
  if (vol != null && Number.isFinite(vol) && vol > 0) {
    out.push(`Sizing reference: scale exposure by target_vol ÷ ${formatPercent(vol)} (current vol) — higher vol implies a smaller position.`);
  }

  const pct = data.percentile_ordinal;
  if (pct != null) {
    if (pct >= 90) out.push(`Risk cap: vol sits in the ${ordinal(pct)} percentile (extreme) — a risk overlay would lower the max weight.`);
    else if (pct <= 10) out.push(`Risk budget: vol sits in the ${ordinal(pct)} percentile (calm) — room for a fuller position within caps.`);
    else out.push(`Risk budget: vol in the ${ordinal(pct)} percentile (mid-range) — no percentile-driven cap implied.`);
  }

  if (/low|weak|poor/i.test(data.estimator_agreement)) {
    out.push("Estimate: estimators disagree (low agreement) — size off the more conservative (higher) vol.");
  }

  if (/unstable|changing|extreme/i.test(data.estimate_stability)) {
    out.push("Smoothing: estimate is unstable — adjust weights gradually rather than snapping to target.");
  } else {
    out.push("Smoothing: estimate is stable — target weight can be tracked closely.");
  }

  return out;
}

function MetaItem({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.1rem" }}>
      <span style={{ fontSize: "0.68rem", color: "var(--text-subtle)" }}>{label}</span>
      <span style={{ fontSize: "0.82rem", fontWeight: 600, fontFamily: mono ? "var(--font-mono, monospace)" : "inherit" }}>
        {value}
      </span>
    </div>
  );
}
*/
// ===== end Strategy signal snapshot =====

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.message} (HTTP ${error.status})`;
  return error instanceof Error ? error.message : "Request failed.";
}

function Muted({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return <div style={{ padding: "1rem", color: tone === "error" ? "var(--danger)" : "var(--text-subtle)" }}>{children}</div>;
}
