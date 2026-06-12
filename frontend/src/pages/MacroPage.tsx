/**
 * ETFs vs Macro page (spec Page 6, Phase 4): the dual-axis ETF-vs-indicator
 * charts, the yield curve, and the macro dashboard. ETF close prices come from
 * the ETF endpoint; indicators from the macro endpoint; yields from yield-curve.
 * Each Plotly chart overlays an ETF/primary line (left axis) and a macro line
 * (right axis) — macro is monthly, so the two traces keep their own date arrays.
 */

import { lazy, Suspense, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { useEtfPrices, useMacro, useYieldCurve } from "../api/hooks";
import type { NamedSeries } from "../api/types";

const PlotlyLineChart = lazy(() => import("../components/charts/PlotlyLineChart"));

const TICKERS = ["TLT", "AGG", "SHY"];

function relabel(series: NamedSeries | undefined, name: string): NamedSeries | undefined {
  return series ? { ...series, name } : undefined;
}

export function MacroPage() {
  const etf = useEtfPrices();
  const macro = useMacro();
  const yc = useYieldCurve();

  const macroSeries = (key: string) => macro.data?.series.find((s) => s.name === key);
  const etfSeries = (ticker: string) => etf.data?.series.find((s) => s.name === ticker);

  if (etf.isLoading || macro.isLoading || yc.isLoading) return <Muted>Loading macro data…</Muted>;
  if (etf.isError || macro.isError || yc.isError) {
    return <Muted tone="error">{errorMessage(etf.error ?? macro.error ?? yc.error)}</Muted>;
  }

  const cpi = relabel(macroSeries("cpi"), "CPI YoY");
  const pmi = relabel(macroSeries("pmi"), "PMI");
  const unemployment = relabel(macroSeries("unemployment"), "Unemployment");
  const sentiment = relabel(macroSeries("consumer_sentiment"), "Consumer Sentiment");
  const fedFunds = relabel(macroSeries("fed_funds"), "Fed Funds");

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>ETFs vs Macro Indicators</h2>
      <p style={{ color: "#666", marginTop: "0.25rem" }}>
        ETF prices vs macro indicators (dual axis), the yield curve, and a macro dashboard.
      </p>

      <Suspense fallback={<Muted>Loading charts…</Muted>}>
        <h3>ETF Prices vs CPI & PMI</h3>
        {TICKERS.map((t) => (
          <Row key={t}>
            <Card title={`${t} vs CPI`}>
              <MacroChart primary={etfSeries(t)} secondary={cpi} yLabel={`${t} Price ($)`} yTickFormat="$,.0f" y2Label="CPI YoY (%)" />
            </Card>
            <Card title={`${t} vs PMI`}>
              <MacroChart primary={etfSeries(t)} secondary={pmi} yLabel={`${t} Price ($)`} yTickFormat="$,.0f" y2Label="PMI" />
            </Card>
          </Row>
        ))}

        <h3 style={{ marginTop: "1.5rem" }}>Yield Curve (10Y / 2Y / Spread)</h3>
        <Card>
          {yc.data ? (
            <PlotlyLineChart
              series={[yc.data.gs10, yc.data.gs2, yc.data.spread]}
              yLabel="Yield (%)"
              yTickFormat=".2f"
              secondaryNames={["10Y-2Y Spread"]}
              y2Label="Spread (%)"
              y2TickFormat=".2f"
              height={440}
            />
          ) : null}
        </Card>

        <h3 style={{ marginTop: "1.5rem" }}>Macro Dashboard</h3>
        <Row>
          <Card title="Unemployment vs Consumer Sentiment">
            <MacroChart primary={unemployment} secondary={sentiment} yLabel="Unemployment (%)" yTickFormat=".1f" y2Label="Sentiment" y2TickFormat=".0f" />
          </Card>
          <Card title="Fed Funds vs CPI">
            <MacroChart primary={fedFunds} secondary={cpi} yLabel="Fed Funds (%)" yTickFormat=".2f" y2Label="CPI YoY (%)" />
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

function Row({ children }: { children: ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "1rem", marginBottom: "1rem" }}>
      {children}
    </div>
  );
}

function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div style={{ border: "1px solid #eee", borderRadius: 8, padding: "0.75rem" }}>
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
  return <div style={{ padding: "1rem", color: tone === "error" ? "#b00020" : "#777" }}>{children}</div>;
}
