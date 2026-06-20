/**
 * TanStack Query hooks over the API client (spec §7.3).
 *
 * Query keys mirror endpoints so they invalidate cleanly. `useHealth` gates the
 * app; the ETF hooks back the ETF Prices page (Phase 1); the scenarios / nav /
 * returns hooks back Tabs 1-2 (Phase 2). Per-view hooks for the rest arrive with
 * their phases.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiPost } from "./client";
import type {
  AssetVolatilitySnapshotResponse,
  BacktestDailyResponse,
  CrossAssetRatioSeriesResponse,
  CrossAssetVolatilityResponse,
  EstimateStabilityResponse,
  EstimatorAgreementResponse,
  VolatilityChartResponse,
  EtfPricesResponse,
  EtfPriceStatsResponse,
  HealthResponse,
  JobStatus,
  ConditionalReturnsResponse,
  ForwardReturnScatterResponse,
  MacroResponse,
  MacroSnapshotResponse,
  RegimeTimelineResponse,
  NavComparisonResponse,
  ReturnsDiagnosticResponse,
  ReturnsFilterMode,
  ReturnsPointDetail,
  ReturnsResponse,
  ScenariosResponse,
  SignalOutcomeDistributionResponse,
  SignalOutcomeResponse,
  StrategiesResponse,
  TearsheetResponse,
  VolatilityContextResponse,
  VolatilityFeaturesResponse,
  VolatilityLatestResponse,
  VolatilityPercentileSeriesResponse,
  VolatilityRatioChangeResponse,
  VolatilityStateTableResponse,
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
  returnsDiagnostic: (params: ReturnsDiagnosticParams) =>
    [
      "returns-diagnostic",
      params.scenarioIds ?? null,
      params.start ?? null,
      params.end ?? null,
      params.filterMode ?? "all",
      params.tableLimit ?? null,
    ] as const,
  tearsheet: (scenarioId: string | null, rfr: number, ppy: number) =>
    ["tearsheet", scenarioId, rfr, ppy] as const,
  dailyRows: (scenarioId: string | null, options: object) => ["daily", scenarioId, options] as const,
  volatilityFeatures: (ticker: string | null, methods?: string[]) =>
    ["vol-features", ticker, methods ?? null] as const,
  volatilityLatest: ["vol-latest"] as const,
  volatilityContext: (ticker: string | null, estimator: string, window: string) =>
    ["vol-context", ticker, estimator, window] as const,
  volatilityPercentile: (ticker: string | null, estimator: string, window: string) =>
    ["vol-percentile", ticker, estimator, window] as const,
  volatilityDerived: (ticker: string | null, estimator: string, view: string) =>
    ["vol-derived", ticker, estimator, view] as const,
  volatilityStateTable: (estimator: string, window: string) =>
    ["vol-state-table", estimator, window] as const,
  volatilityAgreement: (ticker: string | null, window: string) =>
    ["vol-agreement", ticker, window] as const,
  volatilityChart: (ticker: string | null, estimator: string, window: string, view: string) =>
    ["vol-chart", ticker, estimator, window, view] as const,
  estimateStability: (ticker: string | null, estimator: string, window: string) =>
    ["vol-stability", ticker, estimator, window] as const,
  crossAsset: (estimator: string, window: string) => ["vol-cross-asset", estimator, window] as const,
  crossAssetRatio: (pair: string, estimator: string, window: string, view: string) =>
    ["vol-cross-asset-ratio", pair, estimator, window, view] as const,
  signalOutcomes: (
    ticker: string | null,
    estimator: string,
    window: string,
    sampling: string,
    start: string | null,
    end: string | null,
  ) => ["vol-outcomes", ticker, estimator, window, sampling, start, end] as const,
  signalOutcomeConditions: (
    ticker: string | null,
    estimator: string,
    window: string,
    sampling: string,
    start: string | null,
    end: string | null,
  ) => ["vol-outcome-conditions", ticker, estimator, window, sampling, start, end] as const,
  signalOutcomeDistribution: (
    ticker: string | null,
    estimator: string,
    window: string,
    horizon: string,
    sampling: string,
    start: string | null,
    end: string | null,
  ) => ["vol-outcome-dist", ticker, estimator, window, horizon, sampling, start, end] as const,
  signalSnapshot: (ticker: string | null, estimator: string, window: string, asOf: string | null) =>
    ["vol-snapshot", ticker, estimator, window, asOf] as const,
  macro: (indicators?: string[]) => ["macro", indicators ?? null] as const,
  yieldCurve: ["yield-curve"] as const,
  macroSnapshot: ["macro-snapshot"] as const,
  regimeTimeline: ["regime-timeline"] as const,
  conditionalReturns: (etf?: string, minObservations?: number) =>
    ["conditional-returns", etf ?? null, minObservations ?? null] as const,
  forwardReturnScatter: (etf: string, indicator: string, horizon: string) =>
    ["forward-return-scatter", etf, indicator, horizon] as const,
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

export interface ReturnsDiagnosticParams {
  /** Selected scenarios; omit for the server's representative default (~3-5). */
  scenarioIds?: string[];
  /** ISO clamps (the server clips to the data range). */
  start?: string;
  end?: string;
  /** Return-filter applied to the scatter only (boxplot + tables span the full range). */
  filterMode?: ReturnsFilterMode;
  tableLimit?: number;
}

/**
 * Returns Analysis diagnostic payload (scatter + boxplot + worst/best/dispersion
 * tables). Keyed on the full param set so each (scenarios, date range, filter)
 * combination is cached independently; legend toggles + display options stay
 * client-side and never refetch.
 */
export function useReturnsDiagnostic(params: ReturnsDiagnosticParams = {}) {
  return useQuery<ReturnsDiagnosticResponse>({
    queryKey: queryKeys.returnsDiagnostic(params),
    queryFn: () => {
      const search = new URLSearchParams();
      if (params.scenarioIds?.length) search.set("scenario_ids", params.scenarioIds.join(","));
      if (params.start) search.set("start", params.start);
      if (params.end) search.set("end", params.end);
      if (params.filterMode) search.set("filter_mode", params.filterMode);
      if (params.tableLimit != null) search.set("table_limit", String(params.tableLimit));
      const qs = search.toString();
      return apiGet<ReturnsDiagnosticResponse>(
        `/backtest-results/returns-diagnostic${qs ? `?${qs}` : ""}`,
      );
    },
    // The whole grid arrives in one payload and scenario visibility is toggled
    // client-side, so already-fetched (date, filter) combinations should not
    // background-refetch on revisit.
    staleTime: 300_000,
  });
}

/** Rich single-point diagnostic detail for the click drilldown (fetched on demand). */
export function useReturnsPointDetail(scenarioId?: string, date?: string) {
  return useQuery<ReturnsPointDetail>({
    queryKey: ["returns-point", scenarioId ?? null, date ?? null],
    queryFn: () =>
      apiGet<ReturnsPointDetail>(
        `/backtest-results/returns-diagnostic/point?scenario_id=${encodeURIComponent(
          scenarioId!,
        )}&date=${encodeURIComponent(date!)}`,
      ),
    enabled: Boolean(scenarioId && date),
    staleTime: 300_000,
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

/** Latest percentile context for one ticker/estimator/window (Phase 1 card). */
export function useVolatilityContext(ticker: string | undefined, estimator: string, window: string) {
  return useQuery<VolatilityContextResponse>({
    queryKey: queryKeys.volatilityContext(ticker ?? null, estimator, window),
    queryFn: () =>
      apiGet<VolatilityContextResponse>(
        `/volatility-features/context?ticker=${encodeURIComponent(ticker!)}&estimator=${estimator}&window=${window}`,
      ),
    enabled: Boolean(ticker),
    staleTime: 60_000,
  });
}

/** Historical-percentile line for one ticker/estimator/window (Phase 1 percentile view). */
export function useVolatilityPercentile(
  ticker: string | undefined,
  estimator: string,
  window: string,
  options?: QueryOptions,
) {
  return useQuery<VolatilityPercentileSeriesResponse>({
    queryKey: queryKeys.volatilityPercentile(ticker ?? null, estimator, window),
    queryFn: () =>
      apiGet<VolatilityPercentileSeriesResponse>(
        `/volatility-features/percentile?ticker=${encodeURIComponent(ticker!)}&estimator=${estimator}&window=${window}`,
      ),
    enabled: Boolean(ticker) && (options?.enabled ?? true),
    staleTime: 60_000,
  });
}

/** All-asset confirmed diagnostic-state table (Phase 3). */
export function useVolatilityStateTable(estimator: string, window: string) {
  return useQuery<VolatilityStateTableResponse>({
    queryKey: queryKeys.volatilityStateTable(estimator, window),
    queryFn: () =>
      apiGet<VolatilityStateTableResponse>(
        `/volatility-features/state-table?estimator=${estimator}&window=${window}`,
      ),
    staleTime: 60_000,
  });
}

/** Unified chart payload (series + state shading + transition markers) for one view (Phase 6). */
export function useVolatilityChart(
  ticker: string | undefined,
  estimator: string,
  window: string,
  view: "volatility" | "percentile" | "ratio" | "change" | "dispersion" | "vov",
) {
  return useQuery<VolatilityChartResponse>({
    queryKey: queryKeys.volatilityChart(ticker ?? null, estimator, window, view),
    queryFn: () =>
      apiGet<VolatilityChartResponse>(
        `/volatility-features/chart?ticker=${encodeURIComponent(ticker!)}&estimator=${estimator}&window=${window}&view=${view}`,
      ),
    enabled: Boolean(ticker),
    staleTime: 60_000,
  });
}

/** Estimate stability (vol-of-vol percentile + status) for one ticker (Phase 8). */
export function useEstimateStability(ticker: string | undefined, estimator: string, window: string) {
  return useQuery<EstimateStabilityResponse>({
    queryKey: queryKeys.estimateStability(ticker ?? null, estimator, window),
    queryFn: () =>
      apiGet<EstimateStabilityResponse>(
        `/volatility-features/stability?ticker=${encodeURIComponent(ticker!)}&estimator=${estimator}&window=${window}`,
      ),
    enabled: Boolean(ticker),
    staleTime: 60_000,
  });
}

/** Cross-asset relative-vol ratios + risk ranking (Phase 7, monitor only). */
export function useCrossAssetVolatility(estimator: string, window: string) {
  return useQuery<CrossAssetVolatilityResponse>({
    queryKey: queryKeys.crossAsset(estimator, window),
    queryFn: () =>
      apiGet<CrossAssetVolatilityResponse>(`/volatility-features/cross-asset?estimator=${estimator}&window=${window}`),
    staleTime: 60_000,
  });
}

/** One pair's ratio (or its percentile) over time (Phase 7 chart). */
export function useCrossAssetRatioSeries(
  pair: string | undefined,
  estimator: string,
  window: string,
  view: "raw" | "percentile",
) {
  return useQuery<CrossAssetRatioSeriesResponse>({
    queryKey: queryKeys.crossAssetRatio(pair ?? "", estimator, window, view),
    queryFn: () =>
      apiGet<CrossAssetRatioSeriesResponse>(
        `/volatility-features/cross-asset/ratio-series?pair=${encodeURIComponent(pair!)}&estimator=${estimator}&window=${window}&view=${view}`,
      ),
    enabled: Boolean(pair),
    staleTime: 60_000,
  });
}

/** Historical forward outcomes by diagnostic state for one ticker (Phase 9). */
export function useSignalOutcomes(
  ticker: string | undefined,
  estimator: string,
  window: string,
  sampling: "non_overlapping" | "all",
  start?: string,
  end?: string,
) {
  return useQuery<SignalOutcomeResponse>({
    queryKey: queryKeys.signalOutcomes(ticker ?? null, estimator, window, sampling, start ?? null, end ?? null),
    queryFn: () => {
      const params = new URLSearchParams({ ticker: ticker!, estimator, window, sampling });
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      return apiGet<SignalOutcomeResponse>(`/volatility-features/outcomes?${params.toString()}`);
    },
    enabled: Boolean(ticker),
    staleTime: 60_000,
  });
}

/** Forward outcomes for the combined-condition signals for one ticker (Phase 9). */
export function useSignalOutcomeConditions(
  ticker: string | undefined,
  estimator: string,
  window: string,
  sampling: "non_overlapping" | "all",
  start?: string,
  end?: string,
) {
  return useQuery<SignalOutcomeResponse>({
    queryKey: queryKeys.signalOutcomeConditions(ticker ?? null, estimator, window, sampling, start ?? null, end ?? null),
    queryFn: () => {
      const params = new URLSearchParams({ ticker: ticker!, estimator, window, sampling });
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      return apiGet<SignalOutcomeResponse>(`/volatility-features/outcomes/conditions?${params.toString()}`);
    },
    enabled: Boolean(ticker),
    staleTime: 60_000,
  });
}

/** Per-state forward-return distributions at one horizon for the Phase 9 box plot. */
export function useSignalOutcomeDistribution(
  ticker: string | undefined,
  estimator: string,
  window: string,
  horizon: string,
  sampling: "non_overlapping" | "all",
  start?: string,
  end?: string,
) {
  return useQuery<SignalOutcomeDistributionResponse>({
    queryKey: queryKeys.signalOutcomeDistribution(
      ticker ?? null, estimator, window, horizon, sampling, start ?? null, end ?? null,
    ),
    queryFn: () => {
      const params = new URLSearchParams({ ticker: ticker!, estimator, window, horizon, sampling });
      if (start) params.set("start", start);
      if (end) params.set("end", end);
      return apiGet<SignalOutcomeDistributionResponse>(
        `/volatility-features/outcomes/distribution?${params.toString()}`,
      );
    },
    enabled: Boolean(ticker),
    staleTime: 60_000,
  });
}

/** Passive point-in-time signal snapshot for one ticker (Phase 10); as-of defaults to latest. */
export function useAssetSignalSnapshot(
  ticker: string | undefined,
  estimator: string,
  window: string,
  asOf?: string,
) {
  return useQuery<AssetVolatilitySnapshotResponse>({
    queryKey: queryKeys.signalSnapshot(ticker ?? null, estimator, window, asOf ?? null),
    queryFn: () => {
      const params = new URLSearchParams({ ticker: ticker!, estimator, window });
      if (asOf) params.set("as_of", asOf);
      return apiGet<AssetVolatilitySnapshotResponse>(`/volatility-features/snapshot?${params.toString()}`);
    },
    enabled: Boolean(ticker),
    staleTime: 60_000,
  });
}

/** Estimator-agreement summary + per-estimator comparison panel for one ticker (Phase 4). */
export function useEstimatorAgreement(ticker: string | undefined, window: string) {
  return useQuery<EstimatorAgreementResponse>({
    queryKey: queryKeys.volatilityAgreement(ticker ?? null, window),
    queryFn: () =>
      apiGet<EstimatorAgreementResponse>(
        `/volatility-features/agreement?ticker=${encodeURIComponent(ticker!)}&window=${window}`,
      ),
    enabled: Boolean(ticker),
    staleTime: 60_000,
  });
}

/** Term-ratio / volatility-change / estimator-dispersion line (Phase 2/4 chart views). */
export function useVolatilityDerived(
  ticker: string | undefined,
  estimator: string,
  view: "ratio" | "change" | "dispersion",
  options?: QueryOptions,
) {
  return useQuery<VolatilityRatioChangeResponse>({
    queryKey: queryKeys.volatilityDerived(ticker ?? null, estimator, view),
    queryFn: () =>
      apiGet<VolatilityRatioChangeResponse>(
        `/volatility-features/derived?ticker=${encodeURIComponent(ticker!)}&estimator=${estimator}&view=${view}`,
      ),
    enabled: Boolean(ticker) && (options?.enabled ?? true),
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

/** Latest macro snapshot cards (Page 6 snapshot row). */
export function useMacroSnapshot() {
  return useQuery<MacroSnapshotResponse>({
    queryKey: queryKeys.macroSnapshot,
    queryFn: () => apiGet<MacroSnapshotResponse>("/macro/snapshot"),
    staleTime: 60_000,
  });
}

/** Macro-regime timeline + engine duration-support overlay (Page 6). */
export function useRegimeTimeline() {
  return useQuery<RegimeTimelineResponse>({
    queryKey: queryKeys.regimeTimeline,
    queryFn: () => apiGet<RegimeTimelineResponse>("/macro/regime-timeline"),
    staleTime: 60_000,
  });
}

/** Conditional forward-return table by macro regime (Page 6, Phase 5). */
export function useConditionalReturns(etf?: string, minObservations?: number) {
  return useQuery<ConditionalReturnsResponse>({
    queryKey: queryKeys.conditionalReturns(etf, minObservations),
    queryFn: () =>
      apiGet<ConditionalReturnsResponse>(
        `/macro/conditional-returns${buildQuery({
          etf: etf ? [etf] : undefined,
          min_observations: minObservations != null ? [String(minObservations)] : undefined,
        })}`,
      ),
    staleTime: 60_000,
  });
}

/** Δ-macro vs forward-ETF-return scatter (explorer scatter mode); fetched only when `enabled`. */
export function useForwardReturnScatter(etf: string, indicator: string, horizon: string, enabled = true) {
  return useQuery<ForwardReturnScatterResponse>({
    queryKey: queryKeys.forwardReturnScatter(etf, indicator, horizon),
    queryFn: () =>
      apiGet<ForwardReturnScatterResponse>(
        `/macro/forward-return-scatter${buildQuery({ etf: [etf], indicator: [indicator], horizon: [horizon] })}`,
      ),
    staleTime: 60_000,
    enabled,
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

/**
 * Select which registry entry the live run trades (the star toggle). Writes the
 * server-side override and seeds the refreshed registry into the cache so the UI
 * reflects the new live strategy without an extra round-trip.
 */
export function useSetLiveStrategy() {
  const queryClient = useQueryClient();
  return useMutation<StrategiesResponse, Error, string>({
    mutationFn: (name) => apiPost<StrategiesResponse>("/strategies/live", { name }),
    onSuccess: (data) => queryClient.setQueryData(queryKeys.strategies, data),
  });
}

/** Reset the live strategy to the built-in default (clears the override). */
export function useResetLiveStrategy() {
  const queryClient = useQueryClient();
  return useMutation<StrategiesResponse, Error, void>({
    mutationFn: () => apiPost<StrategiesResponse>("/strategies/live/reset"),
    onSuccess: (data) => queryClient.setQueryData(queryKeys.strategies, data),
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
