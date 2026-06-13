/**
 * TanStack Query hooks over the API client (spec §7.3).
 *
 * Query keys mirror endpoints so they invalidate cleanly. `useHealth` gates the
 * app; the ETF hooks back the ETF Prices page (Phase 1); the scenarios / nav /
 * returns hooks back Tabs 1-2 (Phase 2). Per-view hooks for the rest arrive with
 * their phases.
 */

import { useMutation, useQuery } from "@tanstack/react-query";

import { apiGet, apiPost } from "./client";
import type {
  BacktestDailyResponse,
  EtfPricesResponse,
  EtfPriceStatsResponse,
  HealthResponse,
  JobStatus,
  MacroResponse,
  NavComparisonResponse,
  ReturnsResponse,
  ScenariosResponse,
  StrategiesResponse,
  TearsheetResponse,
  VolatilityFeaturesResponse,
  VolatilityLatestResponse,
  YieldCurveResponse,
} from "./types";

export const queryKeys = {
  health: ["health"] as const,
  scenarios: ["scenarios"] as const,
  etfPrices: (tickers?: string[]) => ["etf-prices", tickers ?? null] as const,
  etfPriceStats: (tickers?: string[]) => ["etf-prices", "stats", tickers ?? null] as const,
  navComparison: (scenarioIds?: string[], benchmarks?: string[]) =>
    ["nav-comparison", scenarioIds ?? null, benchmarks ?? null] as const,
  returns: (scenarioIds?: string[]) => ["returns", scenarioIds ?? null] as const,
  tearsheet: (scenarioId: string | null, rfr: number, ppy: number) =>
    ["tearsheet", scenarioId, rfr, ppy] as const,
  dailyRows: (scenarioId: string | null, options: object) => ["daily", scenarioId, options] as const,
  volatilityFeatures: (ticker: string | null, methods?: string[]) =>
    ["vol-features", ticker, methods ?? null] as const,
  volatilityLatest: ["vol-latest"] as const,
  macro: (indicators?: string[]) => ["macro", indicators ?? null] as const,
  yieldCurve: ["yield-curve"] as const,
  strategies: ["strategies"] as const,
};

interface DailyRowsOptions {
  limit?: number;
  offset?: number;
  columns?: string[];
}

interface QueryOptions {
  enabled?: boolean;
}

/** Build a `?a=x,y&b=z` query string from comma-joined array params (omits empties). */
function buildQuery(params: Record<string, string[] | undefined>): string {
  const parts: string[] = [];
  for (const [key, values] of Object.entries(params)) {
    if (values && values.length > 0) parts.push(`${key}=${encodeURIComponent(values.join(","))}`);
  }
  return parts.length > 0 ? `?${parts.join("&")}` : "";
}

/** Poll the DB-exists health gate. Short, retried lightly -- it gates the app. */
export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: queryKeys.health,
    queryFn: () => apiGet<HealthResponse>("/health"),
    retry: 1,
    staleTime: 30_000,
  });
}

/** Distinct persisted scenario ids (endpoint 1) -- the picker source. */
export function useScenarios() {
  return useQuery<ScenariosResponse>({
    queryKey: queryKeys.scenarios,
    queryFn: () => apiGet<ScenariosResponse>("/scenarios"),
    staleTime: 60_000,
  });
}

/** ETF close-price lines (endpoint 6, Tab 4 chart). */
export function useEtfPrices(tickers?: string[]) {
  return useQuery<EtfPricesResponse>({
    queryKey: queryKeys.etfPrices(tickers),
    queryFn: () => apiGet<EtfPricesResponse>(`/etf-prices${buildQuery({ tickers })}`),
  });
}

/** ETF price-statistics table (endpoint 7, Tab 4 table). */
export function useEtfPriceStats(tickers?: string[]) {
  return useQuery<EtfPriceStatsResponse>({
    queryKey: queryKeys.etfPriceStats(tickers),
    queryFn: () => apiGet<EtfPriceStatsResponse>(`/etf-prices/stats${buildQuery({ tickers })}`),
  });
}

/** NAV comparison: scenario lines + dashed benchmarks + summary (endpoint 2, Tab 1). */
export function useNavComparison(
  scenarioIds?: string[],
  benchmarks?: string[],
  options?: QueryOptions,
) {
  return useQuery<NavComparisonResponse>({
    queryKey: queryKeys.navComparison(scenarioIds, benchmarks),
    queryFn: () =>
      apiGet<NavComparisonResponse>(
        `/backtest-results/nav-comparison${buildQuery({ scenario_ids: scenarioIds, benchmarks })}`,
      ),
    enabled: options?.enabled ?? true,
  });
}

/** Daily-returns scatter, columnar (endpoint 3, Tab 2). */
export function useReturns(scenarioIds?: string[], options?: QueryOptions) {
  return useQuery<ReturnsResponse>({
    queryKey: queryKeys.returns(scenarioIds),
    queryFn: () =>
      apiGet<ReturnsResponse>(`/backtest-results/returns${buildQuery({ scenario_ids: scenarioIds })}`),
    enabled: options?.enabled ?? true,
  });
}

/** Full tearsheet for one scenario (endpoint 5, Tab 3). Cached server-side. */
export function useTearsheet(scenarioId?: string, riskFreeRate = 0.02, periodsPerYear = 252) {
  return useQuery<TearsheetResponse>({
    queryKey: queryKeys.tearsheet(scenarioId ?? null, riskFreeRate, periodsPerYear),
    queryFn: () =>
      apiGet<TearsheetResponse>(
        `/tearsheet/${encodeURIComponent(scenarioId!)}?risk_free_rate=${riskFreeRate}&periods_per_year=${periodsPerYear}`,
      ),
    enabled: Boolean(scenarioId),
  });
}

/** Raw daily rows for one scenario, paginated (endpoint 4, Tab 3). */
export function useDailyRows(scenarioId?: string, options?: DailyRowsOptions) {
  return useQuery<BacktestDailyResponse>({
    queryKey: queryKeys.dailyRows(scenarioId ?? null, options ?? {}),
    queryFn: () => {
      const params = new URLSearchParams();
      if (options?.columns?.length) params.set("columns", options.columns.join(","));
      if (options?.limit != null) params.set("limit", String(options.limit));
      if (options?.offset != null) params.set("offset", String(options.offset));
      const qs = params.toString();
      return apiGet<BacktestDailyResponse>(
        `/backtest-results/${encodeURIComponent(scenarioId!)}/daily${qs ? `?${qs}` : ""}`,
      );
    },
    enabled: Boolean(scenarioId),
  });
}

/** Vol estimate lines for one ticker (endpoint 8); all methods fetched, filter client-side. */
export function useVolatilityFeatures(ticker?: string, methods?: string[]) {
  return useQuery<VolatilityFeaturesResponse>({
    queryKey: queryKeys.volatilityFeatures(ticker ?? null, methods),
    queryFn: () =>
      apiGet<VolatilityFeaturesResponse>(
        `/volatility-features?ticker=${encodeURIComponent(ticker!)}${methods?.length ? `&methods=${methods.join(",")}` : ""}`,
      ),
    enabled: Boolean(ticker),
  });
}

/** Latest vol per ticker (endpoint 9). */
export function useVolatilityLatest() {
  return useQuery<VolatilityLatestResponse>({
    queryKey: queryKeys.volatilityLatest,
    queryFn: () => apiGet<VolatilityLatestResponse>("/volatility-features/latest"),
    staleTime: 60_000,
  });
}

/** Macro indicator series (endpoint 10). */
export function useMacro(indicators?: string[]) {
  return useQuery<MacroResponse>({
    queryKey: queryKeys.macro(indicators),
    queryFn: () => apiGet<MacroResponse>(`/macro${buildQuery({ indicators })}`),
    staleTime: 60_000,
  });
}

/** Yield curve: 10Y/2Y + spread (endpoint 11). */
export function useYieldCurve() {
  return useQuery<YieldCurveResponse>({
    queryKey: queryKeys.yieldCurve,
    queryFn: () => apiGet<YieldCurveResponse>("/macro/yield-curve"),
    staleTime: 60_000,
  });
}

/** Strategy registry introspection (endpoint 12). */
export function useStrategies() {
  return useQuery<StrategiesResponse>({
    queryKey: queryKeys.strategies,
    queryFn: () => apiGet<StrategiesResponse>("/strategies"),
    staleTime: 300_000,
  });
}

/** Trigger a backtest run (endpoint 13); returns the created job. */
export function useTriggerBacktest() {
  return useMutation<JobStatus, Error, string[] | undefined>({
    mutationFn: (strategyNames) =>
      apiPost<JobStatus>("/jobs/backtest", { strategy_names: strategyNames ?? null }),
  });
}

/** Poll a backtest job (endpoint 14); auto-refetches while queued/running. */
export function useJob(jobId: string | undefined) {
  return useQuery<JobStatus>({
    queryKey: ["job", jobId ?? null],
    queryFn: () => apiGet<JobStatus>(`/jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1500 : false;
    },
  });
}

/** Cancel a running backtest (terminates its subprocess). */
export function useCancelBacktest() {
  return useMutation<JobStatus, Error, string>({
    mutationFn: (jobId) => apiPost<JobStatus>(`/jobs/${encodeURIComponent(jobId)}/cancel`),
  });
}
