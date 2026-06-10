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
