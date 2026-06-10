/**
 * TanStack Query hooks over the API client (spec §7.3).
 *
 * Query keys mirror endpoints so they invalidate cleanly. `useHealth` gates the
 * app; the ETF hooks back the ETF Prices page (Phase 1); the scenarios / nav /
 * returns hooks back Tabs 1-2 (Phase 2). Per-view hooks for the rest arrive with
 * their phases.
 */

import { useQuery } from "@tanstack/react-query";

import { apiGet } from "./client";
import type {
  EtfPricesResponse,
  EtfPriceStatsResponse,
  HealthResponse,
  NavComparisonResponse,
  ReturnsResponse,
  ScenariosResponse,
} from "./types";

export const queryKeys = {
  health: ["health"] as const,
  scenarios: ["scenarios"] as const,
  etfPrices: (tickers?: string[]) => ["etf-prices", tickers ?? null] as const,
  etfPriceStats: (tickers?: string[]) => ["etf-prices", "stats", tickers ?? null] as const,
  navComparison: (scenarioIds?: string[], benchmarks?: string[]) =>
    ["nav-comparison", scenarioIds ?? null, benchmarks ?? null] as const,
  returns: (scenarioIds?: string[]) => ["returns", scenarioIds ?? null] as const,
};

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
