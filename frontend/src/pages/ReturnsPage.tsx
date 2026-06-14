/**
 * Returns Analysis page (diagnostic redesign).
 *
 * A focused daily-return *diagnostic* tool, not a dense all-scenario poster.
 * The whole scenario grid is fetched once; showing/hiding a scenario is a pure
 * client-side Plotly legend toggle (no refetch), with only the default few drawn
 * visible on load. Family / vol-method / target-vol controls narrow which curves
 * render; date range and the return-filter are server params (changing them
 * refetches once, then caches). Rich per-point context lives in the worst/best/
 * dispersion tables (computed server-side over the full grid) and the on-demand
 * click drilldown; the boxplot mirrors the visible curves.
 */

import { lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { useReturnsDiagnostic, useReturnsPointDetail } from "../api/hooks";
import type { ReturnsFilterMode, ScenarioMeta, TableModel } from "../api/types";
import type { ScatterPointSelection } from "../components/charts/ReturnsScatter";
import { DataTable, type Column } from "../components/tables/DataTable";
import { formatPercent } from "../lib/format";

const ReturnsScatter = lazy(() => import("../components/charts/ReturnsScatter"));
const ReturnsBoxplot = lazy(() => import("../components/charts/ReturnsBoxplot"));

const ALL = "All";

const FILTER_MODE_LABELS: Record<ReturnsFilterMode, string> = {
  all: "All daily returns",
  abs_gt_1pct: "|return| > 1%",
  abs_gt_2pct: "|return| > 2%",
  worst_1pct: "Worst 1% by scenario",
  best_1pct: "Best 1% by scenario",
  extremes_20: "Best & worst 20 by scenario",
};

const VOL_METHOD_LABELS: Record<string, string> = {
  roll: "Rolling",
  covlb: "Covariance lookback",
  ewmacov: "EWMA covariance",
};

type DatePreset = "full" | "covid" | "rate2022" | "last3y" | "custom";

const DATE_PRESET_LABELS: Record<DatePreset, string> = {
  full: "Full history",
  covid: "COVID shock",
  rate2022: "2022 rate shock",
  last3y: "Last 3 years",
  custom: "Custom",
};

export function ReturnsPage() {
  // --- control state (all client-side; scenario visibility lives in `hidden`) ---
  const [family, setFamily] = useState<string>(ALL);
  const [volMethod, setVolMethod] = useState<string>(ALL);
  const [targetVol, setTargetVol] = useState<string>(ALL);
  const [datePreset, setDatePreset] = useState<DatePreset>("full");
  const [customStart, setCustomStart] = useState<string>("");
  const [customEnd, setCustomEnd] = useState<string>("");
  const [filterMode, setFilterMode] = useState<ReturnsFilterMode>("all");
  const [showRefLines, setShowRefLines] = useState(true);
  const [showDist, setShowDist] = useState(true);
  const [rawIds, setRawIds] = useState(false);
  const [hidden, setHidden] = useState<ReadonlySet<string> | null>(null);
  const [point, setPoint] = useState<ScatterPointSelection | null>(null);

  // Date ceiling (for "Last 3 years") arrives with the payload, then held in state.
  const [dateMax, setDateMax] = useState<string | null>(null);
  const range = computeRange(datePreset, dateMax, customStart, customEnd);

  // ONE fetch for the whole grid; date range + return-filter are the only server
  // params, so scenario show/hide never refetches.
  const diag = useReturnsDiagnostic({ start: range.start, end: range.end, filterMode });

  useEffect(() => {
    if (diag.data?.date_max) setDateMax(diag.data.date_max);
  }, [diag.data?.date_max]);

  const available = diag.data?.available_scenarios ?? [];
  const allIds = useMemo(() => available.map((m) => m.scenario_id), [available]);

  // Universe = scenarios passing the family / vol / target-vol filters (client-side).
  const universeIds = useMemo(() => {
    const ids = available.filter((m) => matchesFilters(m, family, volMethod, targetVol)).map((m) => m.scenario_id);
    return new Set(ids);
  }, [available, family, volMethod, targetVol]);

  // Until the user touches the legend, derive visibility from default_visible
  // synchronously (avoids a one-frame flash of all curves before the init effect).
  const hiddenSet = useMemo<ReadonlySet<string>>(() => {
    if (hidden !== null) return hidden;
    if (!diag.data) return new Set<string>();
    const visible = new Set(diag.data.default_visible);
    return new Set(allIds.filter((id) => !visible.has(id)));
  }, [hidden, diag.data, allIds]);
  const series = diag.data?.series ?? [];
  const distribution = diag.data?.distribution ?? [];
  const renderedSeries = series.filter((s) => universeIds.has(s.scenario_id));
  const visibleDistribution = distribution.filter(
    (d) => universeIds.has(d.scenario_id) && !hiddenSet.has(d.scenario_id),
  );

  function toggleScenario(id: string) {
    setHidden((prev) => {
      const base = new Set(prev ?? hiddenSet);
      if (base.has(id)) base.delete(id);
      else base.add(id);
      return base;
    });
  }

  function isolateScenario(id: string) {
    const visibleNow = [...universeIds].filter((x) => !hiddenSet.has(x));
    if (visibleNow.length === 1 && visibleNow[0] === id) {
      // Already isolated -> show every scenario in the current universe.
      setHidden(new Set(allIds.filter((x) => !universeIds.has(x))));
    } else {
      setHidden(new Set(allIds.filter((x) => x !== id)));
    }
  }

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Returns Analysis</h2>
      <p style={{ color: "var(--text-muted)", marginTop: "0.25rem" }}>
        Inspect daily return behaviour across scenarios. Toggle curves with the chart legend (click to
        show/hide, double-click to isolate); use the filters to find stress periods and outliers, and
        click a point for its full diagnostic. A microscope, not a ranking — use NAV / Tearsheet for
        overall performance.
      </p>

      {/* ---- Controls ---- */}
      <div style={controlPanelStyle}>
        <div style={controlRowStyle}>
          <Dropdown label="Family" value={family} onChange={setFamily}
            options={[ALL, ...uniqueValues(available.map((m) => m.family))]} />
          <Dropdown label="Vol method" value={volMethod} onChange={setVolMethod}
            options={[ALL, ...uniqueValues(available.map((m) => m.vol_method))]}
            renderOption={(o) => (o === ALL ? ALL : VOL_METHOD_LABELS[o] ?? o)} />
          <Dropdown label="Target vol" value={targetVol} onChange={setTargetVol}
            options={[ALL, ...uniqueValues(available.map((m) => tvKey(m.target_vol)))]}
            renderOption={(o) => (o === ALL ? ALL : `${o}%`)} />
          <Dropdown label="Date range" value={datePreset}
            onChange={(v) => setDatePreset(v as DatePreset)}
            options={Object.keys(DATE_PRESET_LABELS) as DatePreset[]}
            renderOption={(o) => DATE_PRESET_LABELS[o as DatePreset]} />
          {datePreset === "custom" && (
            <>
              <DateField label="From" value={customStart} onChange={setCustomStart} />
              <DateField label="To" value={customEnd} onChange={setCustomEnd} />
            </>
          )}
          <Dropdown label="Show" value={filterMode}
            onChange={(v) => setFilterMode(v as ReturnsFilterMode)}
            options={Object.keys(FILTER_MODE_LABELS) as ReturnsFilterMode[]}
            renderOption={(o) => FILTER_MODE_LABELS[o as ReturnsFilterMode]} />
        </div>

        <div style={{ ...controlRowStyle, marginTop: "0.6rem" }}>
          <Toggle label="Reference lines" checked={showRefLines} onChange={setShowRefLines} />
          <Toggle label="Distribution chart" checked={showDist} onChange={setShowDist} />
          <Toggle label="Raw IDs in legend" checked={rawIds} onChange={setRawIds} />
          <span style={{ color: "var(--text-faint)", fontSize: "0.8rem" }}>
            Tip: click a legend entry to show/hide a scenario; double-click to isolate.
          </span>
        </div>
      </div>

      {/* ---- Scatter ---- */}
      <section style={{ marginBottom: "1.5rem" }}>
        {diag.isLoading ? (
          <Status>Loading returns…</Status>
        ) : diag.isError ? (
          <Status tone="error">{errorMessage(diag.error)}</Status>
        ) : renderedSeries.length === 0 ? (
          <Status>No scenarios match the current filters. Widen the family / vol / target-vol selection.</Status>
        ) : (
          <Suspense fallback={<Status>Loading chart…</Status>}>
            <ReturnsScatter
              series={renderedSeries}
              hidden={hiddenSet}
              onToggleScenario={toggleScenario}
              onIsolateScenario={isolateScenario}
              showReferenceLines={showRefLines}
              useRawLabels={rawIds}
              onSelectPoint={setPoint}
            />
          </Suspense>
        )}
      </section>

      {point && <DrilldownPanel point={point} onClose={() => setPoint(null)} />}

      {/* ---- Diagnostic tables (server-computed over the full scenario grid) ---- */}
      {diag.data && (
        <>
          <DiagnosticSection
            title="Worst Daily Returns"
            subtitle="Most severe daily losses across all scenarios for the selected date range."
            table={diag.data.worst}
          />
          <DiagnosticSection
            title="Best Daily Returns"
            subtitle="Largest daily gains across all scenarios for the selected date range."
            table={diag.data.best}
          />
          <DiagnosticSection
            title="Largest Scenario Dispersion Days"
            subtitle="Dates where scenario choice mattered most (max − min daily return)."
            table={diag.data.dispersion}
          />
        </>
      )}

      {/* ---- Distribution boxplot (mirrors the visible curves) ---- */}
      {showDist && visibleDistribution.length > 0 && (
        <section style={{ marginTop: "1.5rem" }}>
          <h3 style={sectionTitleStyle}>Return Distribution by Scenario</h3>
          <p style={subtitleStyle}>One box per visible scenario; toggle curves in the chart legend above.</p>
          <Suspense fallback={<Muted>Loading chart…</Muted>}>
            <ReturnsBoxplot distribution={visibleDistribution} useRawLabels={rawIds} />
          </Suspense>
        </section>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Date-range helpers
// --------------------------------------------------------------------------- //
function computeRange(
  preset: DatePreset,
  dateMax: string | null,
  customStart: string,
  customEnd: string,
): { start?: string; end?: string } {
  switch (preset) {
    case "covid":
      return { start: "2020-02-01", end: "2020-06-30" };
    case "rate2022":
      return { start: "2022-01-01", end: "2022-12-31" };
    case "last3y": {
      if (!dateMax) return {};
      const end = new Date(dateMax);
      const start = new Date(end);
      start.setFullYear(start.getFullYear() - 3);
      return { start: start.toISOString().slice(0, 10), end: dateMax };
    }
    case "custom":
      return { start: customStart || undefined, end: customEnd || undefined };
    case "full":
    default:
      return {};
  }
}

// --------------------------------------------------------------------------- //
// Scenario filtering
// --------------------------------------------------------------------------- //
function matchesFilters(m: ScenarioMeta, family: string, vol: string, tv: string): boolean {
  if (family !== ALL && m.family !== family) return false;
  if (vol !== ALL && m.vol_method !== vol) return false;
  if (tv !== ALL && tvKey(m.target_vol) !== tv) return false;
  return true;
}

/** A target-vol fraction (0.03) -> the discrete dropdown key ("3"); null -> "—". */
function tvKey(targetVol: number | null): string {
  if (targetVol == null) return "—";
  const pct = targetVol * 100;
  return Number.isInteger(pct) ? String(pct) : String(Number(pct.toFixed(1)));
}

function uniqueValues(values: (string | null)[]): string[] {
  return [...new Set(values.filter((v): v is string => v != null && v !== ""))].sort();
}

// --------------------------------------------------------------------------- //
// Diagnostic drilldown panel (fetches the clicked point's rich detail on demand)
// --------------------------------------------------------------------------- //
function DrilldownPanel({ point, onClose }: { point: ScatterPointSelection; onClose: () => void }) {
  const detail = useReturnsPointDetail(point.scenarioId, point.date);
  return (
    <section style={drilldownStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <strong>Selected Return Event</strong>
        <button type="button" onClick={onClose} style={closeButtonStyle}>Close</button>
      </div>
      <div style={{ marginTop: "0.5rem", fontSize: "0.9rem", lineHeight: 1.5, fontVariantNumeric: "tabular-nums" }}>
        {detail.isLoading ? (
          <span style={{ color: "var(--text-subtle)" }}>Loading {point.scenarioLabel} @ {point.date}…</span>
        ) : detail.isError ? (
          <span style={{ color: "var(--danger)" }}>{errorMessage(detail.error)}</span>
        ) : detail.data?.lines.length ? (
          detail.data.lines.map((l, i) => <div key={i}>{l}</div>)
        ) : (
          <span style={{ color: "var(--text-subtle)" }}>No diagnostic detail for this point.</span>
        )}
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------- //
// Diagnostic tables (generic TableModel -> DataTable, column formatters by name)
// --------------------------------------------------------------------------- //
type Row = Record<string, unknown>;

interface ColSpec {
  header: string;
  align?: "left" | "right";
  numeric?: boolean;
  render: (v: unknown) => ReactNode;
}

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
const text = (v: unknown): string => (v == null ? "" : String(v));
const mono = (v: unknown): ReactNode => (
  <span style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "0.78rem" }}>{text(v)}</span>
);
const pct = (digits: number) => (v: unknown) => formatPercent(num(v), digits);

const COLUMN_SPECS: Record<string, ColSpec> = {
  date: { header: "Date", render: text },
  scenario_label: { header: "Scenario", render: text },
  scenario_id: { header: "Raw ID", render: mono },
  daily_return: { header: "Return", align: "right", numeric: true, render: pct(2) },
  primary_holding: { header: "Primary", render: text },
  tlt_weight: { header: "TLT", align: "right", numeric: true, render: pct(0) },
  agg_weight: { header: "AGG", align: "right", numeric: true, render: pct(0) },
  shy_weight: { header: "SHY", align: "right", numeric: true, render: pct(0) },
  growth_regime: { header: "Growth", render: text },
  curve_state: { header: "Curve", render: text },
  macro_supports_duration: { header: "Supports dur.", render: text },
  turnover: { header: "Turnover", align: "right", numeric: true, render: pct(1) },
  total_cost: { header: "Cost", align: "right", numeric: true, render: pct(2) },
  dispersion: { header: "Dispersion", align: "right", numeric: true, render: pct(2) },
  best_scenario_label: { header: "Best scenario", render: text },
  best_scenario_id: { header: "Best raw ID", render: mono },
  best_return: { header: "Best", align: "right", numeric: true, render: pct(2) },
  worst_scenario_label: { header: "Worst scenario", render: text },
  worst_scenario_id: { header: "Worst raw ID", render: mono },
  worst_return: { header: "Worst", align: "right", numeric: true, render: pct(2) },
  scenario_count: { header: "# Scen", align: "right", numeric: true, render: text },
};

function columnsFor(table: TableModel): Column<Row>[] {
  return table.columns.map((key): Column<Row> => {
    const spec = COLUMN_SPECS[key] ?? { header: key, render: text };
    return {
      key,
      header: spec.header,
      align: spec.align,
      render: (row) => spec.render(row[key]),
      sortValue: spec.numeric
        ? (row) => num(row[key])
        : (row) => (row[key] == null ? null : String(row[key])),
    };
  });
}

function DiagnosticSection({ title, subtitle, table }: { title: string; subtitle: string; table: TableModel }) {
  const columns = useMemo(() => columnsFor(table), [table]);
  return (
    <section style={{ marginTop: "1.5rem" }}>
      <h3 style={sectionTitleStyle}>{title}</h3>
      <p style={subtitleStyle}>{subtitle}</p>
      <div style={{ overflowX: "auto" }}>
        <DataTable columns={columns} rows={table.rows as Row[]} />
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------- //
// Small reusable control widgets
// --------------------------------------------------------------------------- //
function Dropdown<T extends string>({
  label, value, onChange, options, renderOption,
}: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: readonly T[];
  renderOption?: (o: T) => string;
}) {
  return (
    <label style={fieldStyle}>
      <span style={fieldLabelStyle}>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value as T)} style={selectStyle}>
        {options.map((o) => (
          <option key={o} value={o}>{renderOption ? renderOption(o) : o}</option>
        ))}
      </select>
    </label>
  );
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label style={fieldStyle}>
      <span style={fieldLabelStyle}>{label}</span>
      <input type="date" value={value} onChange={(e) => onChange(e.target.value)} style={selectStyle} />
    </label>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem", color: "var(--text-2)" }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

// --------------------------------------------------------------------------- //
// Styles + status
// --------------------------------------------------------------------------- //
const controlPanelStyle: React.CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "0.75rem",
  marginBottom: "1.25rem",
};
const controlRowStyle: React.CSSProperties = { display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap" };
const fieldStyle: React.CSSProperties = { display: "inline-flex", alignItems: "center", gap: "0.4rem" };
const fieldLabelStyle: React.CSSProperties = { color: "var(--text-3)", fontSize: "0.85rem" };
const selectStyle: React.CSSProperties = { padding: "0.3rem 0.45rem", borderRadius: 6, border: "1px solid var(--border-strong)", fontSize: "0.85rem" };
const sectionTitleStyle: React.CSSProperties = { marginBottom: "0.25rem" };
const subtitleStyle: React.CSSProperties = { color: "var(--text-faint)", fontSize: "0.8rem", margin: "0 0 0.5rem" };
const drilldownStyle: React.CSSProperties = { border: "1px solid var(--accent-border)", background: "var(--accent-bg-soft)", borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1.25rem" };
const closeButtonStyle: React.CSSProperties = { padding: "0.15rem 0.55rem", borderRadius: 6, border: "1px solid var(--border-strong)", background: "var(--surface)", fontSize: "0.78rem", cursor: "pointer" };

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.message} (HTTP ${error.status})`;
  return error instanceof Error ? error.message : "Request failed.";
}

function Status({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return <div style={{ padding: "1.5rem", color: tone === "error" ? "var(--danger)" : "var(--text-muted)" }}>{children}</div>;
}

function Muted({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return <div style={{ padding: "1rem", color: tone === "error" ? "var(--danger)" : "var(--text-subtle)" }}>{children}</div>;
}
