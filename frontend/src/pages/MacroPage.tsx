/**
 * ETFs vs Macro page (spec Page 6, Phase 4): the dual-axis ETF-vs-indicator
 * charts, the yield curve, and the macro dashboard. ETF close prices come from
 * the ETF endpoint; indicators from the macro endpoint; yields from yield-curve.
 * Each Plotly chart overlays an ETF/primary line (left axis) and a macro line
 * (right axis) — macro is monthly, so the two traces keep their own date arrays.
 */

import { lazy, Suspense, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import {
  useConditionalReturns,
  useEtfPrices,
  useForwardReturnScatter,
  useMacro,
  useMacroSnapshot,
  useRegimeTimeline,
  useYieldCurve,
} from "../api/hooks";
import type { CategoricalSeries, MacroSnapshotCard, NamedSeries } from "../api/types";
import { InfoTooltip } from "../components/InfoTooltip";
import { DataTable, type Column } from "../components/tables/DataTable";
import { useTheme } from "../theme/ThemeContext";

const PlotlyLineChart = lazy(() => import("../components/charts/PlotlyLineChart"));
const ForwardReturnScatter = lazy(() => import("../components/charts/ForwardReturnScatter"));

const TICKERS = ["TLT", "AGG", "SHY"];

function relabel(series: NamedSeries | undefined, name: string): NamedSeries | undefined {
  return series ? { ...series, name } : undefined;
}

// Indicators this page needs: the macro-overview charts plus the explorer's
// level+change menu (derived `cpi_yoy`, not the raw CPI index — see the
// correctness fixes in api/services/macro.py). The explorer's dropdown is built
// from whatever the server returns, labelled via each series' `meta.label`.
const MACRO_INDICATORS = [
  "cpi_yoy", "cpi_yoy_change_3m", "pmi", "activity_change_3m",
  "unemployment", "unemployment_change_3m", "consumer_sentiment",
  "fed_funds", "fed_funds_change_3m", "real_policy_rate",
  "gs2", "gs10", "curve_spread",
  "yield_2y_change_3m", "yield_10y_change_3m", "curve_spread_change_3m",
];

// d3 tick format for a macro series, derived from its meta.unit.
function unitTickFormat(unit: unknown): string {
  switch (unit) {
    case "pct_frac": return ".1%"; // decimal fraction → percent
    case "pct": return ".2f";      // already a percent number
    case "pp": return ".2f";
    default: return "";            // "level" / unknown → Plotly default
  }
}

export function MacroPage() {
  const etf = useEtfPrices();
  const macro = useMacro(MACRO_INDICATORS);
  const yc = useYieldCurve();
  const snapshot = useMacroSnapshot();
  const regimeTimeline = useRegimeTimeline();

  const macroSeries = (key: string) => macro.data?.series.find((s) => s.name === key);
  const etfSeries = (ticker: string) => etf.data?.series.find((s) => s.name === ticker);

  if (etf.isLoading || macro.isLoading || yc.isLoading) return <Muted>Loading macro data…</Muted>;
  if (etf.isError || macro.isError || yc.isError) {
    return <Muted tone="error">{errorMessage(etf.error ?? macro.error ?? yc.error)}</Muted>;
  }

  // `cpi_yoy` is year-over-year inflation (a decimal fraction → rendered with the
  // ".1%" tick format), used by the macro-overview "Fed Funds vs CPI YoY" chart.
  const cpiYoy = relabel(macroSeries("cpi_yoy"), "CPI YoY");
  const unemployment = relabel(macroSeries("unemployment"), "Unemployment");
  const sentiment = relabel(macroSeries("consumer_sentiment"), "Consumer Sentiment");
  const fedFunds = relabel(macroSeries("fed_funds"), "Fed Funds");

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: 0 }}>
        <h2 style={{ margin: 0 }}>ETFs vs Macro Indicators</h2>
        <InfoTooltip label="How to read these charts" width={360}>
          Dual-axis charts share a time axis but have independent scales — that can make unrelated series look
          correlated. Read them for timing and regime, not correlation.
        </InfoTooltip>
      </div>
      <p style={{ color: "var(--text-muted)", marginTop: "0.25rem" }}>
        ETF adjusted-close prices vs macro indicators (dual axis), the yield curve, and a macro dashboard.
      </p>

      <SnapshotCards query={snapshot} />

      <Suspense fallback={<Muted>Loading charts…</Muted>}>
        <h3>ETF &amp; Macro Explorer</h3>
        <MacroExplorer etfFor={etfSeries} macroList={macro.data?.series ?? []} />

        <h3 style={{ marginTop: "1.5rem" }}>Yield Curve (10Y / 2Y / Spread)</h3>
        {yc.data?.current_regime ? (
          <p style={{ margin: "0 0 0.5rem", fontSize: "0.9rem" }}>
            Current curve regime: <strong style={{ color: "var(--accent)" }}>{yc.data.current_regime}</strong>
          </p>
        ) : null}
        <Card>
          {yc.data ? (
            <PlotlyLineChart
              series={[yc.data.gs10, yc.data.gs2, yc.data.spread]}
              yLabel="Yield (%)"
              yTickFormat=".2f"
              secondaryNames={["10Y-2Y Spread"]}
              y2Label="Spread (%)"
              y2TickFormat=".2f"
              referenceLines={[{ value: 0, axis: "y2" }]}
              bands={(yc.data.inverted_intervals as { start: string; end: string }[]).map((iv) => ({ ...iv, color: INVERSION_BAND }))}
              height={440}
            />
          ) : null}
        </Card>
        <p style={captionStyle}>
          Red bands mark curve inversion (negative 10Y-2Y spread). Inversion signals restrictive policy and
          expected slowing — it is not, by itself, an immediate signal to buy duration (TLT).
        </p>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "1.5rem" }}>
          <h3 style={{ margin: 0 }}>Macro Regime Timeline</h3>
          <InfoTooltip label="About the regime timeline" width={380}>
            A transparent, rule-based macro regime shaded behind the ETF line. These are explanatory dashboard
            labels — not the engine's allocation regimes — and the bond preferences shown are economic priors,
            not backtested results. Switch the overlay to compare against the engine's duration-support signal.
          </InfoTooltip>
        </div>
        <RegimeTimeline etfFor={etfSeries} query={regimeTimeline} />

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "1.5rem" }}>
          <h3 style={{ margin: 0 }}>Conditional Forward Returns</h3>
          <InfoTooltip label="About conditional returns" width={400}>
            For each macro regime, the average forward total return of TLT/AGG/SHY over the following 1/3/6/12
            months — measured only after the regime was knowable (lagged, no look-ahead). This is descriptive,
            not predictive: overlapping monthly horizons make the observations non-independent, so treat the
            counts as weak evidence and thin regimes with caution.
          </InfoTooltip>
        </div>
        <ConditionalReturns />

        <h3 style={{ marginTop: "1.5rem" }}>Macro Dashboard</h3>
        <Row>
          <Card title="Unemployment vs Consumer Sentiment">
            <MacroChart primary={unemployment} secondary={sentiment} yLabel="Unemployment (%)" yTickFormat=".1f" y2Label="Sentiment" y2TickFormat=".0f" />
          </Card>
          <Card title="Fed Funds vs CPI YoY">
            <MacroChart primary={fedFunds} secondary={cpiYoy} yLabel="Fed Funds (%)" yTickFormat=".2f" y2Label="CPI YoY (%)" y2TickFormat=".1%" />
          </Card>
        </Row>
      </Suspense>
    </div>
  );
}

function MacroChart({
  primary,
  secondary,
  yLabel,
  yTickFormat,
  y2Label,
  y2TickFormat = ".2f",
}: {
  primary?: NamedSeries;
  secondary?: NamedSeries;
  yLabel: string;
  yTickFormat: string;
  y2Label: string;
  y2TickFormat?: string;
}) {
  const series = [primary, secondary].filter((s): s is NamedSeries => Boolean(s));
  if (series.length === 0) return <Muted>No data.</Muted>;
  return (
    <PlotlyLineChart
      series={series}
      yLabel={yLabel}
      yTickFormat={yTickFormat}
      secondaryNames={secondary ? [secondary.name] : undefined}
      y2Label={y2Label}
      y2TickFormat={y2TickFormat}
      height={320}
    />
  );
}

const captionStyle: React.CSSProperties = {
  color: "var(--text-faint)",
  fontSize: "0.8rem",
  margin: "0 0 0.75rem",
};

// --------------------------------------------------------------------------- //
// Snapshot cards (latest reading per indicator, each with its own date)
// --------------------------------------------------------------------------- //
const DIRECTION_ARROW: Record<string, string> = { up: "▲", down: "▼", flat: "→" };
// Rising = green, falling = red (per request); flat is muted.
const DIRECTION_COLOR: Record<string, string> = {
  up: "var(--success)",
  down: "var(--danger)",
  flat: "var(--text-faint)",
};

/** Format a card value by its unit (see services/macro.py for the vocabulary). */
function formatSnapshotValue(value: number | string | null, unit: string | null | undefined): string {
  if (value === null) return "—";
  if (typeof value === "string") return value;
  switch (unit) {
    case "pct_frac": return `${(value * 100).toFixed(1)}%`; // decimal fraction → percent
    case "pct": return `${value.toFixed(2)}%`;              // already a percent number
    case "pp": return `${value.toFixed(2)} pp`;
    default: return value.toFixed(2);                       // "level"
  }
}

/** The 3-month change, magnitude only (direction is shown via the arrow). */
function formatSnapshotChange(change: number | null | undefined, unit: string | null | undefined): string | null {
  if (change == null) return null;
  const magnitude = unit === "pct_frac" ? Math.abs(change) * 100 : Math.abs(change);
  return unit === "level" ? magnitude.toFixed(2) : `${magnitude.toFixed(2)} pp`;
}

function SnapshotCards({ query }: { query: ReturnType<typeof useMacroSnapshot> }) {
  if (query.isLoading) return <Muted>Loading snapshot…</Muted>;
  if (query.isError || !query.data) return null; // supplementary — never block the charts
  return (
    <section style={{ margin: "1.25rem 0 1.75rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.75rem" }}>
        <span style={{ fontWeight: 600, fontSize: "0.95rem" }}>Latest readings</span>
        <InfoTooltip label="About the snapshot" width={340}>
          Latest available reading per indicator — each card shows its own observation date, since monthly series
          update at different times. As of {query.data.as_of}.
        </InfoTooltip>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))", gap: "1rem" }}>
        {query.data.cards.map((card) => (
          <SnapshotCardTile key={card.key} card={card} />
        ))}
      </div>
    </section>
  );
}

function SnapshotCardTile({ card }: { card: MacroSnapshotCard }) {
  const change = formatSnapshotChange(card.change_3m, card.unit);
  const changeColor = card.direction ? DIRECTION_COLOR[card.direction] ?? "var(--text-faint)" : "var(--text-faint)";
  return (
    <div style={{ border: "1px solid var(--border-soft)", borderRadius: 8, padding: "0.8rem 0.9rem", background: "var(--surface-raised)" }}>
      <div style={{ fontSize: "0.72rem", color: "var(--text-subtle)", textTransform: "uppercase", letterSpacing: "0.02em", display: "flex", justifyContent: "space-between", gap: "0.4rem" }}>
        <span>{card.label}</span>
        {card.is_stale ? <span title="No recent update" style={{ color: "var(--danger)" }}>stale</span> : null}
      </div>
      <div style={{ fontSize: "1.2rem", marginTop: "0.35rem", fontVariantNumeric: "tabular-nums", fontFamily: "var(--font-data)" }}>
        {formatSnapshotValue(card.value, card.unit)}
      </div>
      <div style={{ fontSize: "0.74rem", color: changeColor, marginTop: "0.3rem" }}>
        {card.direction && change ? `${DIRECTION_ARROW[card.direction] ?? ""} ${change} · 3m` : " "}
      </div>
      <div style={{ fontSize: "0.68rem", color: "var(--text-faint)", marginTop: "0.35rem" }}>
        as of {card.observation_date ?? "—"}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// ETF & Macro Explorer (selectors + display modes) — replaces the six fixed charts
// --------------------------------------------------------------------------- //
type ExplorerMode = "dual" | "indexed" | "scatter";
type DateRange = "full" | "10y" | "5y" | "3y";
const FWD_HORIZONS = ["1m", "3m", "6m", "12m"];

const RANGE_YEARS: Record<Exclude<DateRange, "full">, number> = { "10y": 10, "5y": 5, "3y": 3 };

/** ISO start date for a range preset (null = full history), relative to the ETF's last point. */
function rangeStartISO(range: DateRange, etf: NamedSeries): string | null {
  if (range === "full" || etf.points.length === 0) return null;
  const d = new Date(etf.points[etf.points.length - 1].date);
  d.setFullYear(d.getFullYear() - RANGE_YEARS[range]);
  return d.toISOString().slice(0, 10);
}

/** Keep only points on/after `startISO` (ISO strings sort lexicographically). */
function clip(series: NamedSeries, startISO: string | null): NamedSeries {
  if (!startISO) return series;
  return { ...series, points: series.points.filter((p) => p.date >= startISO) };
}

/** Rebase to 100 at the first non-null point; no-op if the base isn't meaningful (≈0). */
function indexTo100(series: NamedSeries): NamedSeries {
  const base = series.points.find((p) => p.value != null)?.value;
  if (base == null || Math.abs(base) < 1e-9) return series;
  return {
    ...series,
    points: series.points.map((p) => ({ ...p, value: p.value == null ? null : (p.value / base) * 100 })),
  };
}

function MacroExplorer({
  etfFor,
  macroList,
}: {
  etfFor: (ticker: string) => NamedSeries | undefined;
  macroList: NamedSeries[];
}) {
  const [ticker, setTicker] = useState(TICKERS[0]);
  const [macroKey, setMacroKey] = useState("cpi_yoy");
  const [range, setRange] = useState<DateRange>("full");
  const [mode, setMode] = useState<ExplorerMode>("dual");
  const [horizon, setHorizon] = useState("3m");

  const etf = etfFor(ticker);
  const macro = macroList.find((s) => s.name === macroKey) ?? macroList[0];
  // Scatter data is server-computed (forward returns); fetched only in scatter mode.
  const scatter = useForwardReturnScatter(ticker, macro?.name ?? "", horizon, mode === "scatter" && Boolean(etf && macro));
  if (!etf || !macro) return <Muted>No data.</Muted>;

  const macroLabel = (macro.meta?.["label"] as string | undefined) ?? macro.name;
  const startISO = rangeStartISO(range, etf);
  const etfClipped = clip(etf, startISO);
  const macroClipped = clip(macro, startISO);

  let chart: ReactNode;
  if (mode === "scatter") {
    chart = scatter.isLoading ? (
      <Muted>Loading scatter…</Muted>
    ) : scatter.isError || !scatter.data ? (
      <Muted tone="error">Could not load scatter.</Muted>
    ) : (
      <ForwardReturnScatter
        points={scatter.data.points}
        xLabel={scatter.data.x_label}
        xTickFormat={unitTickFormat(scatter.data.x_unit)}
        yLabel={`${ticker} ${horizon} forward return`}
        height={420}
      />
    );
  } else if (mode === "indexed") {
    const e = { ...indexTo100(etfClipped), name: `${ticker} (indexed)` };
    const m = { ...indexTo100(macroClipped), name: `${macroLabel} (indexed)` };
    chart = <PlotlyLineChart series={[e, m]} yLabel="Indexed to 100 (start of range)" yTickFormat=".0f" height={420} />;
  } else {
    const e = { ...etfClipped, name: `${ticker} Adj. Close` };
    const m = { ...macroClipped, name: macroLabel };
    chart = (
      <PlotlyLineChart
        series={[e, m]}
        yLabel={`${ticker} Adj. Close ($)`}
        yTickFormat="$,.0f"
        secondaryNames={[m.name]}
        y2Label={macroLabel}
        y2TickFormat={unitTickFormat(macro.meta?.["unit"])}
        height={420}
      />
    );
  }

  return (
    <Card>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center", marginBottom: "0.5rem" }}>
        <ExplorerField label="ETF">
          <select value={ticker} onChange={(e) => setTicker(e.target.value)} style={explorerSelect}>
            {TICKERS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </ExplorerField>
        <ExplorerField label="Macro indicator">
          <select value={macro.name} onChange={(e) => setMacroKey(e.target.value)} style={explorerSelect}>
            {macroList.map((s) => (
              <option key={s.name} value={s.name}>{(s.meta?.["label"] as string | undefined) ?? s.name}</option>
            ))}
          </select>
        </ExplorerField>
        <ExplorerField label="Range">
          <select value={range} onChange={(e) => setRange(e.target.value as DateRange)} style={explorerSelect}>
            <option value="full">Full history</option>
            <option value="10y">Last 10 years</option>
            <option value="5y">Last 5 years</option>
            <option value="3y">Last 3 years</option>
          </select>
        </ExplorerField>
        <ExplorerField label="Display">
          <select value={mode} onChange={(e) => setMode(e.target.value as ExplorerMode)} style={explorerSelect}>
            <option value="dual">Dual axis</option>
            <option value="indexed">Indexed to 100</option>
            <option value="scatter">Scatter vs forward return</option>
          </select>
        </ExplorerField>
        {mode === "scatter" && (
          <ExplorerField label="Forward horizon">
            <select value={horizon} onChange={(e) => setHorizon(e.target.value)} style={explorerSelect}>
              {FWD_HORIZONS.map((h) => <option key={h} value={h}>{h}</option>)}
            </select>
          </ExplorerField>
        )}
      </div>
      {chart}
      <p style={{ ...captionStyle, margin: "0.5rem 0 0" }}>
        {mode === "dual"
          ? "Dual-axis: the two series have independent scales — compare timing and regime, not levels."
          : mode === "indexed"
            ? "Both series rebased to 100 at the start of the visible range. Meaningful only for positive levels (e.g. prices, yields), not for change/spread series."
            : "Each point is one month: the macro reading (x) vs the ETF's subsequent return (y), measured after the reading was knowable. Association is not causation; overlapping windows make points non-independent."}
      </p>
    </Card>
  );
}

function ExplorerField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
      <span style={{ color: "var(--text-3)", fontSize: "0.85rem" }}>{label}</span>
      {children}
    </label>
  );
}

const explorerSelect: React.CSSProperties = {
  padding: "0.3rem 0.45rem",
  borderRadius: 6,
  border: "1px solid var(--border-strong)",
  fontSize: "0.85rem",
};

// --------------------------------------------------------------------------- //
// Macro regime timeline (ETF line + regime background shading)
// --------------------------------------------------------------------------- //
const INVERSION_BAND = "rgba(214, 39, 40, 0.10)";

// Base RGB per regime label; bands use low alpha, legend swatches higher. These
// are constant data-meaning colours (not theme chrome).
const MACRO_REGIME_RGB: Record<string, string> = {
  "Stable Growth": "120, 120, 120",
  "Inflationary Tightening": "214, 39, 40",
  "Disinflationary Slowdown": "31, 119, 180",
  "Stagflation Risk": "148, 0, 33",
  "Easing Transition": "44, 160, 44",
};
const ENGINE_REGIME_RGB: Record<string, string> = {
  "No duration support": "120, 120, 120",
  "Supports duration": "44, 160, 44",
};

// High-contrast mode swaps in vivid, maximally-distinct neon hues so the regimes
// read clearly behind the ETF line on a black canvas. Blue is avoided — the
// contrast theme's axes/font are already electric blue.
const MACRO_REGIME_RGB_CONTRAST: Record<string, string> = {
  "Stable Growth": "240, 240, 20",        // neon yellow
  "Inflationary Tightening": "255, 40, 40", // neon red
  "Disinflationary Slowdown": "180, 90, 255", // neon purple
  "Stagflation Risk": "255, 16, 160",     // hot pink
  "Easing Transition": "57, 255, 20",     // neon green
};
const ENGINE_REGIME_RGB_CONTRAST: Record<string, string> = {
  "No duration support": "255, 145, 0",   // neon orange
  "Supports duration": "57, 255, 20",     // neon green
};

type RegimeOverlay = "dashboard" | "engine";

/** Contiguous same-label spans of a categorical series → coloured chart bands. */
function regimeBands(
  series: CategoricalSeries | null | undefined,
  rgbFor: (label: string) => string | undefined,
  alpha = 0.16,
): { start: string; end: string; color: string }[] {
  if (!series) return [];
  const pts = series.points;
  const out: { start: string; end: string; color: string }[] = [];
  let i = 0;
  while (i < pts.length) {
    const label = pts[i].label;
    if (label == null) {
      i++;
      continue;
    }
    let j = i;
    while (j + 1 < pts.length && pts[j + 1].label === label) j++;
    const rgb = rgbFor(label);
    if (rgb) {
      const end = j + 1 < pts.length ? pts[j + 1].date : pts[j].date; // contiguous bands
      out.push({ start: pts[i].date, end, color: `rgba(${rgb}, ${alpha})` });
    }
    i = j + 1;
  }
  return out;
}

function RegimeTimeline({
  etfFor,
  query,
}: {
  etfFor: (ticker: string) => NamedSeries | undefined;
  query: ReturnType<typeof useRegimeTimeline>;
}) {
  const { mode } = useTheme();
  const [ticker, setTicker] = useState(TICKERS[0]);
  const [overlay, setOverlay] = useState<RegimeOverlay>("dashboard");

  if (query.isLoading) return <Muted>Loading regimes…</Muted>;
  if (query.isError || !query.data) return null; // supplementary — never block the page

  const contrast = mode === "contrast";
  const engineAvailable = Boolean(query.data.engine_regime);
  const useEngine = overlay === "engine" && engineAvailable;
  const series = useEngine ? query.data.engine_regime : query.data.regime;
  const rgbMap = useEngine
    ? (contrast ? ENGINE_REGIME_RGB_CONTRAST : ENGINE_REGIME_RGB)
    : (contrast ? MACRO_REGIME_RGB_CONTRAST : MACRO_REGIME_RGB);
  // Vivid neon fills need a touch more opacity to read on the black contrast canvas.
  const bands = regimeBands(series, (label) => rgbMap[label], contrast ? 0.4 : 0.16);
  const etf = etfFor(ticker);

  const legendEntries: [string, string][] = useEngine
    ? Object.keys(ENGINE_REGIME_RGB).map((label) => [
        label,
        label === "Supports duration"
          ? "Engine's macro signal favours duration"
          : "Engine's macro signal does not favour duration",
      ])
    : Object.entries(query.data.legend);

  return (
    <Card>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center", marginBottom: "0.5rem" }}>
        <ExplorerField label="ETF">
          <select value={ticker} onChange={(e) => setTicker(e.target.value)} style={explorerSelect}>
            {TICKERS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </ExplorerField>
        <ExplorerField label="Overlay">
          <select value={overlay} onChange={(e) => setOverlay(e.target.value as RegimeOverlay)} style={explorerSelect}>
            <option value="dashboard">Dashboard regime</option>
            <option value="engine" disabled={!engineAvailable}>Engine: supports duration</option>
          </select>
        </ExplorerField>
      </div>
      {etf ? (
        <PlotlyLineChart
          series={[{ ...etf, name: `${ticker} Adj. Close` }]}
          yLabel={`${ticker} Adj. Close ($)`}
          yTickFormat="$,.0f"
          bands={bands}
          height={420}
        />
      ) : (
        <Muted>No ETF data.</Muted>
      )}
      <div style={{ display: "flex", gap: "0.6rem 1.25rem", flexWrap: "wrap", marginTop: "0.6rem" }}>
        {legendEntries.map(([label, desc]) => (
          <span key={label} style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.78rem", color: "var(--text-3)" }}>
            <span style={{ width: 12, height: 12, borderRadius: 3, flex: "0 0 auto", background: `rgba(${rgbMap[label] ?? "120, 120, 120"}, 0.55)` }} />
            <span><strong>{label}</strong> — {desc}</span>
          </span>
        ))}
      </div>
    </Card>
  );
}

// --------------------------------------------------------------------------- //
// Conditional forward returns (regime × ETF table)
// --------------------------------------------------------------------------- //
type CondRow = Record<string, unknown>;
const condNum = (v: unknown): number | null => (typeof v === "number" ? v : null);
const condPct = (v: unknown, digits = 1): string => (typeof v === "number" ? `${(v * 100).toFixed(digits)}%` : "—");

const CONDITIONAL_COLUMNS: Column<CondRow>[] = [
  { key: "etf", header: "ETF" },
  {
    key: "regime",
    header: "Regime",
    render: (r) =>
      r.thin ? (
        <span title="Few observations — weak evidence">
          {String(r.regime)} <span style={{ color: "var(--text-faint)" }}>· thin</span>
        </span>
      ) : (
        String(r.regime)
      ),
    sortValue: (r) => (r.regime == null ? null : String(r.regime)),
  },
  { key: "n", header: "Obs", align: "right", render: (r) => String(r.n ?? "—"), sortValue: (r) => condNum(r.n) },
  { key: "next_1m_mean", header: "1M", align: "right", render: (r) => condPct(r.next_1m_mean), sortValue: (r) => condNum(r.next_1m_mean) },
  { key: "next_3m_mean", header: "3M", align: "right", render: (r) => condPct(r.next_3m_mean), sortValue: (r) => condNum(r.next_3m_mean) },
  { key: "next_6m_mean", header: "6M", align: "right", render: (r) => condPct(r.next_6m_mean), sortValue: (r) => condNum(r.next_6m_mean) },
  { key: "next_12m_mean", header: "12M", align: "right", render: (r) => condPct(r.next_12m_mean), sortValue: (r) => condNum(r.next_12m_mean) },
  { key: "hit_rate_3m", header: "3M Hit", align: "right", render: (r) => condPct(r.hit_rate_3m, 0), sortValue: (r) => condNum(r.hit_rate_3m) },
  { key: "median_3m", header: "3M Median", align: "right", render: (r) => condPct(r.median_3m), sortValue: (r) => condNum(r.median_3m) },
];

function ConditionalReturns() {
  const [etf, setEtf] = useState<string>("All");
  const query = useConditionalReturns(etf === "All" ? undefined : etf);

  if (query.isLoading) return <Muted>Loading conditional returns…</Muted>;
  if (query.isError || !query.data) return <Muted tone="error">Could not load conditional returns.</Muted>;

  const rows = query.data.table.rows as CondRow[];
  return (
    <Card>
      <div style={{ display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap", marginBottom: "0.6rem" }}>
        <ExplorerField label="ETF">
          <select value={etf} onChange={(e) => setEtf(e.target.value)} style={explorerSelect}>
            <option value="All">All</option>
            {TICKERS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </ExplorerField>
        <span style={{ color: "var(--text-faint)", fontSize: "0.8rem" }}>
          Mean forward total return after each regime (1/3/6/12 months); 3M hit rate = share of positive 3-month windows.
        </span>
      </div>
      <div style={{ overflowX: "auto" }}>
        <DataTable columns={CONDITIONAL_COLUMNS} rows={rows} />
      </div>
      <ul style={{ margin: "0.6rem 0 0", paddingLeft: "1.1rem", color: "var(--text-faint)", fontSize: "0.78rem", lineHeight: 1.5 }}>
        {query.data.notes.map((note, i) => (
          <li key={i}>{note}</li>
        ))}
      </ul>
    </Card>
  );
}

function Row({ children }: { children: ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "1rem", marginBottom: "1rem" }}>
      {children}
    </div>
  );
}

function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div style={{ border: "1px solid var(--border-soft)", borderRadius: 8, padding: "0.75rem" }}>
      {title ? <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>{title}</div> : null}
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
