/**
 * TypeScript mirror of the API's Pydantic contract (spec §4.2, §7.4).
 *
 * The authoritative types are GENERATED from the live OpenAPI schema into
 * `schema.d.ts` via `npm run gen:api` (spec §7.4: drift becomes a compile
 * error, the frontend analogue of the repo's pyright contract check). App code
 * imports the friendly aliases below, which are *derived from* the generated
 * schema where it covers them (so a contract change surfaces here at compile
 * time) and hand-written for the shared chart primitives the schema inlines.
 */

import type { components } from "./schema";

/** Response of `GET /api/v1/health`, sourced from the generated OpenAPI schema. */
export type HealthResponse = components["schemas"]["HealthResponse"];

/** Response of `GET /api/v1/etf-prices` (Tab 4): one close-price NamedSeries per ticker. */
export type EtfPricesResponse = components["schemas"]["EtfPricesResponse"];

/** A single row of the ETF price-statistics table (Tab 4); raw numbers, not formatted (§4.1). */
export type PriceStat = components["schemas"]["PriceStat"];

/** Response of `GET /api/v1/etf-prices/stats` (Tab 4 table). */
export type EtfPriceStatsResponse = components["schemas"]["EtfPriceStatsResponse"];

/** Response of `GET /api/v1/scenarios`: the persisted scenario ids + count. */
export type ScenariosResponse = components["schemas"]["ScenariosResponse"];

/** Response of `GET /api/v1/backtest-results/nav-comparison` (Tab 1). */
export type NavComparisonResponse = components["schemas"]["NavComparisonResponse"];

/** One row of the Tab 1 performance-summary table. */
export type ScenarioSummaryRow = components["schemas"]["ScenarioSummaryRow"];

/** Response of `GET /api/v1/backtest-results/returns` (Tab 2, columnar). */
export type ReturnsResponse = components["schemas"]["ReturnsResponse"];

/** One scenario's columnar daily-return series (Tab 2). */
export type ReturnsScatterSeries = components["schemas"]["ReturnsScatterSeries"];

/** Response of `GET /api/v1/backtest-results/returns-diagnostic` (Returns Analysis redesign). */
export type ReturnsDiagnosticResponse = components["schemas"]["ReturnsDiagnosticResponse"];

/** One selected scenario's enriched scatter points + per-point hover (diagnostic). */
export type ReturnsDiagnosticSeries = components["schemas"]["ReturnsDiagnosticSeries"];

/** One scenario's full date-range return distribution (boxplot input). */
export type ReturnsDistributionSeries = components["schemas"]["ReturnsDistributionSeries"];

/** Rich single-point diagnostic detail (click drilldown), fetched on demand. */
export type ReturnsPointDetail = components["schemas"]["ReturnsPointDetail"];

/** A scenario's readable label + parsed metadata (Returns Analysis filters/picker). */
export type ScenarioMeta = components["schemas"]["ScenarioMeta"];

/** The six return-filter modes the Returns Analysis scatter offers. */
export type ReturnsFilterMode =
  | "all"
  | "abs_gt_1pct"
  | "abs_gt_2pct"
  | "worst_1pct"
  | "best_1pct"
  | "extremes_20";

/** Response of `GET /api/v1/tearsheet/{scenario_id}` (Tab 3). */
export type TearsheetResponse = components["schemas"]["TearsheetResponse"];

/** The flat 26-field tearsheet metrics object. */
export type TearsheetMetricsModel = components["schemas"]["TearsheetMetricsModel"];

/** Response of `GET /api/v1/backtest-results/{scenario_id}/daily` (Tab 3 raw table). */
export type BacktestDailyResponse = components["schemas"]["BacktestDailyResponse"];

/** Response of `GET /api/v1/volatility-features` (Tab 5 chart). */
export type VolatilityFeaturesResponse = components["schemas"]["VolatilityFeaturesResponse"];

/** Response of `GET /api/v1/volatility-features/latest` (Tab 5 table). */
export type VolatilityLatestResponse = components["schemas"]["VolatilityLatestResponse"];

/** One latest-vol row (Tab 5 table). */
export type VolLatestRow = components["schemas"]["VolLatestRow"];

/** Response of `GET /api/v1/macro` (Page 6). */
export type MacroResponse = components["schemas"]["MacroResponse"];

/** Response of `GET /api/v1/macro/yield-curve` (Page 6). */
export type YieldCurveResponse = components["schemas"]["YieldCurveResponse"];

/** Response of `GET /api/v1/strategies` (registry introspection). */
export type StrategiesResponse = components["schemas"]["StrategiesResponse"];

/** One flattened strategy summary. */
export type StrategySummary = components["schemas"]["StrategySummary"];

/** A backtest job's state (`POST /jobs/backtest`, `GET /jobs/{id}`). */
export type JobStatus = components["schemas"]["JobStatus"];

/** A single (x, y) chart point; `value` is `null` for NaN/Inf (API §6). */
export interface SeriesPoint {
  date: string; // "YYYY-MM-DD"
  value: number | null;
}

/** A named chart trace: legend label + its (x, y) points. */
export interface NamedSeries {
  name: string;
  points: SeriesPoint[];
  meta?: Record<string, unknown> | null;
}

/** A generic table: column order + list-of-records rows. */
export interface TableModel {
  columns: string[];
  rows: Record<string, unknown>[];
}
