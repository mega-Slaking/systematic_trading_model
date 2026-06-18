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
import {
  useEstimatorAgreement,
  useVolatilityChart,
  useVolatilityContext,
  useVolatilityLatest,
  useVolatilityStateTable,
} from "../api/hooks";
import type {
  EstimatorAgreementResponse,
  EstimatorComparisonRow,
  NamedSeries,
  VolatilityContextResponse,
  VolatilityStateRow,
  VolLatestRow,
} from "../api/types";
import { DataTable, type Column } from "../components/tables/DataTable";
import { formatPercent, formatRatio } from "../lib/format";

const PlotlyLineChart = lazy(() => import("../components/charts/PlotlyLineChart"));

const VOL_METHODS: Record<string, string> = {
  rolling_20: "Rolling 20d",
  rolling_60: "Rolling 60d",
  ewma_94: "EWMA λ=0.94",
  ewma_97: "EWMA λ=0.97",
  garch: "GARCH(1,1)",
};

const WINDOWS = ["3Y", "5Y", "10Y", "Full"] as const;
const METHOD_KEYS = Object.keys(VOL_METHODS);
type View = "volatility" | "percentile" | "ratio" | "change" | "dispersion";

const CHART_LABELS: Record<View, string> = {
  volatility: "Annualized volatility",
  percentile: "Historical percentile",
  ratio: "20D / 60D ratio",
  change: "Relative volatility change",
  dispersion: "Estimator dispersion (relative)",
};

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
  const latest = useVolatilityLatest();
  const tickers = (latest.data?.rows ?? []).map((r) => r.ticker);

  const [ticker, setTicker] = useState<string>("");
  const activeTicker = ticker || (tickers.includes("TLT") ? "TLT" : tickers[0]) || "";

  // Per-ticker available estimators come from the latest-values row (non-null methods).
  const latestRow = (latest.data?.rows ?? []).find((r) => r.ticker === activeTicker);
  const available = latestRow
    ? METHOD_KEYS.filter((m) => (latestRow as Record<string, unknown>)[m] != null)
    : METHOD_KEYS;

  const [view, setView] = useState<View>("volatility");
  const [windowKey, setWindowKey] = useState<string>("5Y");
  const [refEstimator, setRefEstimator] = useState<string>("rolling_20");
  const activeEstimator = available.includes(refEstimator)
    ? refEstimator
    : available.includes("rolling_20")
      ? "rolling_20"
      : available[0] ?? "rolling_20";

  const ctx = useVolatilityContext(activeTicker || undefined, activeEstimator, windowKey);
  const chart = useVolatilityChart(activeTicker || undefined, activeEstimator, windowKey, view);
  const stateTable = useVolatilityStateTable(activeEstimator, windowKey);
  const agreement = useEstimatorAgreement(activeTicker || undefined, windowKey);

  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [showShading, setShowShading] = useState(true);
  const [showMarkers, setShowMarkers] = useState(false);

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
          .map((r) => ({ start: r.start, end: r.end, color: stateBandColor(r.state) }))
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

      {/* --- volatility state + context card (Phases 1–4) --- */}
      <ContextCard
        ticker={activeTicker}
        estimator={activeEstimator}
        data={ctx.data}
        isLoading={ctx.isLoading}
        agreement={agreement.data}
      />

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

      <section style={{ marginBottom: "2rem" }}>
        {renderChart()}
        {showShading ? <StateLegend /> : null}
      </section>

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
  data,
  isLoading,
  agreement,
}: {
  ticker: string;
  estimator: string;
  data: VolatilityContextResponse | undefined;
  isLoading: boolean;
  agreement: EstimatorAgreementResponse | undefined;
}) {
  const insufficient = data?.insufficient_history ?? false;
  const level = data?.volatility_level ?? "—";
  const confirmed = data?.confirmed_state ?? "—";
  const instantaneous = data?.instantaneous_state;

  return (
    <div
      style={{
        border: "1px solid var(--border-strong)", borderRadius: 8, padding: "0.9rem 1rem",
        marginBottom: "1.25rem", background: "var(--surface)",
      }}
    >
      {/* headline: confirmed state + as-of */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
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
        <p style={{ margin: "0.6rem 0 0.8rem", fontSize: "0.85rem", color: "var(--text-muted)", maxWidth: 820 }}>
          {data.state_explanation}
        </p>
      ) : null}

      {isLoading ? null : insufficient ? (
        <span style={{ color: "var(--text-muted)" }}>Insufficient history</span>
      ) : (
        <>
          <div style={{ display: "flex", gap: "1.75rem", alignItems: "center", flexWrap: "wrap" }}>
            <Stat label="Current" value={formatPercent(data?.current_volatility ?? null)} />
            <Stat label={`${data?.historical_window ?? ""} percentile`} value={ordinal(data?.percentile_ordinal ?? null)} />
            <LabeledBadge label="Level" text={level} style={levelStyle(level)} />
            <Stat label="20D direction" value={data?.direction ?? "—"} />
            <Stat label="20D change" value={formatPercent(data?.change_20d ?? null, 1)} />
            <Stat label="20D / 60D" value={formatRatio(data?.term_ratio ?? null)} />
            <Stat label="Term state" value={data?.term_state ?? "—"} />
          </div>
          {/* Phase 4: estimator agreement */}
          <div style={{
            display: "flex", gap: "1.75rem", alignItems: "center", flexWrap: "wrap",
            marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border-strong)",
          }}>
            <Stat label="Agreement" value={data?.estimator_agreement ?? "—"} />
            <Stat label="Absolute spread" value={formatPP(data?.absolute_spread ?? null)} />
            <Stat label="Relative dispersion" value={formatPercent(data?.relative_dispersion ?? null, 1)} />
            <Stat label="Highest" value={agreement?.highest_estimator ?? "—"} />
            <Stat label="Lowest" value={agreement?.lowest_estimator ?? "—"} />
          </div>
          {/* Phase 5: price / volatility context */}
          <div style={{
            display: "flex", gap: "1.75rem", alignItems: "center", flexWrap: "wrap",
            marginTop: "0.75rem", paddingTop: "0.75rem", borderTop: "1px solid var(--border-strong)",
          }}>
            <Stat label="Price / Vol context" value={data?.price_volatility_context ?? "—"} />
            <Stat label="20D asset return" value={formatPercent(data?.asset_return_20d ?? null, 1)} />
            <Stat label="20D vol change" value={formatPercent(data?.vol_change_20d ?? null, 1)} />
          </div>
        </>
      )}
    </div>
  );
}

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
  const states = ["Calm", "Early Expansion", "Stress Expansion", "Persistent Stress", "Normalisation", "Shock"];
  return (
    <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center", marginTop: "0.6rem", fontSize: "0.78rem", color: "var(--text-subtle)" }}>
      <span style={{ fontWeight: 600 }}>Confirmed state:</span>
      {states.map((s) => {
        const fill = stateBandColor(s);
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
      <span style={{ fontStyle: "italic" }}>Calm / Unknown are unshaded. Markers = regime change.</span>
    </div>
  );
}

/** Faint shading fill per notable state; Calm/Unknown return null (unshaded) to keep the chart clean. */
function stateBandColor(state: string): string | null {
  switch (state) {
    case "Shock":
      return "rgba(220,38,38,0.20)";
    case "Stress Expansion":
      return "rgba(220,38,38,0.11)";
    case "Persistent Stress":
      return "rgba(234,88,12,0.11)";
    case "Early Expansion":
      return "rgba(217,119,6,0.09)";
    case "Normalisation":
      return "rgba(37,99,235,0.09)";
    default: // Calm, Unknown
      return null;
  }
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

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.message} (HTTP ${error.status})`;
  return error instanceof Error ? error.message : "Request failed.";
}

function Muted({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return <div style={{ padding: "1rem", color: tone === "error" ? "var(--danger)" : "var(--text-subtle)" }}>{children}</div>;
}
