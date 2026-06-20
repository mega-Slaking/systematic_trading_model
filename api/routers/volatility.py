"""Volatility-features router (spec endpoints 8 + 9, Tab 5)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas.volatility import (
    AssetVolatilitySnapshotResponse,
    CrossAssetRatioSeriesResponse,
    CrossAssetVolatilitySnapshotResponse,
    CrossAssetVolatilityResponse,
    EstimateStabilityResponse,
    EstimatorAgreementResponse,
    SignalOutcomeDistributionResponse,
    SignalOutcomeResponse,
    VolatilityAuditResponse,
    VolatilityChartResponse,
    VolatilityContextResponse,
    VolatilityFeaturesResponse,
    VolatilityLatestResponse,
    VolatilityPercentileSeriesResponse,
    VolatilityRatioChangeResponse,
    VolatilityStateTableResponse,
)
from api.services import volatility as service

router = APIRouter(prefix="/volatility-features", tags=["volatility"])


def _split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None


@router.get("", response_model=VolatilityFeaturesResponse, summary="Vol estimate lines for a ticker")
def volatility_features(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    methods: str | None = Query(None, description="Comma-separated method keys. Default: all available."),
) -> VolatilityFeaturesResponse:
    """Per-method annualized-vol lines for one ticker (Tab 5 chart)."""
    return service.get_volatility_for_ticker(ticker.upper(), _split_csv(methods))


@router.get("/latest", response_model=VolatilityLatestResponse, summary="Latest vol per ticker")
def volatility_latest() -> VolatilityLatestResponse:
    """Latest annualized vol per method per ticker (Tab 5 table)."""
    return service.get_volatility_latest()


@router.get("/audit", response_model=VolatilityAuditResponse, summary="Surface data-contract warnings")
def volatility_audit() -> VolatilityAuditResponse:
    """Phase 0 data-contract diagnostics for the persisted surface (read-only)."""
    return service.get_volatility_audit()


@router.get("/chart", response_model=VolatilityChartResponse, summary="Unified chart data (series + shading + transitions)")
def volatility_chart(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    estimator: str = Query("rolling_20", description="Reference estimator key."),
    window: str = Query("5Y", description="Historical window: 3Y | 5Y | 10Y | Full."),
    view: str = Query("volatility", description="View: volatility | percentile | ratio | change | dispersion."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> VolatilityChartResponse:
    """Typed chart payload for the Phase 6 diagnostic chart (no server-built figure)."""
    try:
        return service.get_volatility_chart(ticker.upper(), estimator, window, view, min_periods)
    except ValueError as exc:  # unknown estimator / window / view
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/context", response_model=VolatilityContextResponse, summary="Latest percentile context")
def volatility_context(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    estimator: str = Query("rolling_20", description="Reference estimator key."),
    window: str = Query("5Y", description="Historical window: 3Y | 5Y | 10Y | Full."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> VolatilityContextResponse:
    """Current vol + historical percentile + level for one ticker (Phase 1 card)."""
    try:
        return service.get_volatility_context(ticker.upper(), estimator, window, min_periods)
    except ValueError as exc:  # unknown estimator / window
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/percentile", response_model=VolatilityPercentileSeriesResponse, summary="Historical percentile line")
def volatility_percentile(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    estimator: str = Query("rolling_20", description="Reference estimator key."),
    window: str = Query("5Y", description="Historical window: 3Y | 5Y | 10Y | Full."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> VolatilityPercentileSeriesResponse:
    """The 0.0–1.0 historical-percentile line for the Phase 1 percentile view."""
    try:
        return service.get_volatility_percentile_series(ticker.upper(), estimator, window, min_periods)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/state-table", response_model=VolatilityStateTableResponse, summary="All-asset confirmed-state table")
def volatility_state_table(
    estimator: str = Query("rolling_20", description="Reference estimator key."),
    window: str = Query("5Y", description="Historical window: 3Y | 5Y | 10Y | Full."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> VolatilityStateTableResponse:
    """Latest confirmed diagnostic state per asset (Phase 3 all-asset table)."""
    try:
        return service.get_volatility_state_table(estimator, window, min_periods)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/cross-asset", response_model=CrossAssetVolatilityResponse, summary="Cross-asset relative vol + risk ranking")
def volatility_cross_asset(
    estimator: str = Query("rolling_20", description="Reference estimator key (consistent across assets)."),
    window: str = Query("5Y", description="Historical window for the ratio percentiles."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> CrossAssetVolatilityResponse:
    """Per-pair relative-vol ratios (+ own percentile) and the all-asset risk ranking (monitor only)."""
    try:
        return service.get_cross_asset_volatility(estimator, window, min_periods)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/cross-asset/ratio-series", response_model=CrossAssetRatioSeriesResponse, summary="One pair's ratio / percentile line")
def volatility_cross_asset_ratio_series(
    pair: str = Query(..., description="Asset pair 'A/B', e.g. TLT/AGG (required)."),
    estimator: str = Query("rolling_20", description="Reference estimator key."),
    window: str = Query("5Y", description="Historical window for the percentile view."),
    view: str = Query("raw", description="raw | percentile."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> CrossAssetRatioSeriesResponse:
    """The selected pair's raw ratio or its historical percentile over time (Phase 7 chart)."""
    try:
        return service.get_cross_asset_ratio_series(pair, estimator, window, view, min_periods)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/stability", response_model=EstimateStabilityResponse, summary="Estimate stability (vol-of-vol)")
def volatility_stability(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    estimator: str = Query("rolling_20", description="Reference estimator key."),
    window: str = Query("5Y", description="Historical window for the stability percentile."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> EstimateStabilityResponse:
    """Vol-of-vol percentile + status (raw value is debug/methodology only)."""
    try:
        return service.get_estimate_stability(ticker.upper(), estimator, window, min_periods)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/outcomes", response_model=SignalOutcomeResponse, summary="Historical forward outcomes by state")
def volatility_outcomes(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    estimator: str = Query("rolling_20", description="Reference estimator key (drives the state)."),
    window: str = Query("5Y", description="Historical window for the state percentile."),
    sampling: str = Query("non_overlapping", description="non_overlapping (default) | all (override)."),
    start: str | None = Query(None, description="ISO start clamp on the signal date (inclusive)."),
    end: str | None = Query(None, description="ISO end clamp on the signal date (inclusive)."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> SignalOutcomeResponse:
    """Forward returns / drawdowns / hit rates by confirmed diagnostic state (Phase 9).

    Non-overlapping sampling is the default; hard minimum-sample gates suppress
    full stats for inadequate samples. Outcomes describe the sample only.
    """
    try:
        return service.get_signal_outcomes(
            ticker.upper(), estimator, window, sampling, start, end, min_periods
        )
    except ValueError as exc:  # unknown estimator / window / sampling
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/outcomes/conditions", response_model=SignalOutcomeResponse, summary="Forward outcomes by combined condition")
def volatility_outcome_conditions(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    estimator: str = Query("rolling_20", description="Reference estimator key (drives the conditions)."),
    window: str = Query("5Y", description="Historical window for the percentiles."),
    sampling: str = Query("non_overlapping", description="non_overlapping (default) | all (override)."),
    start: str | None = Query(None, description="ISO start clamp on the signal date (inclusive)."),
    end: str | None = Query(None, description="ISO end clamp on the signal date (inclusive)."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> SignalOutcomeResponse:
    """Forward outcomes for the combined-condition signals (Phase 9, added incrementally).

    Same alignment and minimum-sample gates as ``/outcomes``; ``state`` carries the
    condition label. Every defined condition appears (gated when too rare).
    """
    try:
        return service.get_signal_outcome_conditions(
            ticker.upper(), estimator, window, sampling, start, end, min_periods
        )
    except ValueError as exc:  # unknown estimator / window / sampling
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/outcomes/distribution", response_model=SignalOutcomeDistributionResponse, summary="Forward-return distribution by state")
def volatility_outcome_distribution(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    estimator: str = Query("rolling_20", description="Reference estimator key (drives the state)."),
    window: str = Query("5Y", description="Historical window for the state percentile."),
    horizon: str = Query("1M", description="Forward horizon: 1M | 3M | 6M."),
    sampling: str = Query("non_overlapping", description="non_overlapping (default) | all (override)."),
    start: str | None = Query(None, description="ISO start clamp on the signal date (inclusive)."),
    end: str | None = Query(None, description="ISO end clamp on the signal date (inclusive)."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> SignalOutcomeDistributionResponse:
    """Per-state forward-return samples at one horizon for the Phase 9 box plot."""
    try:
        return service.get_signal_outcome_distribution(
            ticker.upper(), estimator, window, horizon, sampling, start, end, min_periods
        )
    except ValueError as exc:  # unknown estimator / window / horizon / sampling
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/snapshot", response_model=AssetVolatilitySnapshotResponse, summary="Passive point-in-time signal snapshot")
def volatility_snapshot(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    estimator: str = Query("rolling_20", description="Reference estimator key."),
    window: str = Query("5Y", description="Historical window: 3Y | 5Y | 10Y | Full."),
    as_of: str | None = Query(None, description="ISO as-of date; default = latest surface date."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> AssetVolatilitySnapshotResponse:
    """Phase 10 passive snapshot: Phase 1–8 diagnostics + reproducibility metadata at an as-of date.

    Strategy/risk layers *could* consume this typed snapshot; producing it changes
    no allocation, sizing, or weight. Point-in-time via the existing as-of path.
    """
    try:
        return service.get_asset_signal_snapshot(ticker.upper(), estimator, window, as_of, min_periods)
    except ValueError as exc:  # unknown estimator / window / bad date
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/snapshot/cross-asset", response_model=CrossAssetVolatilitySnapshotResponse, summary="Passive all-asset signal snapshot")
def volatility_snapshot_cross_asset(
    estimator: str = Query("rolling_20", description="Reference estimator key."),
    window: str = Query("5Y", description="Historical window: 3Y | 5Y | 10Y | Full."),
    as_of: str | None = Query(None, description="ISO as-of date; default = latest surface date."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> CrossAssetVolatilitySnapshotResponse:
    """Phase 10 passive all-asset snapshot: per-asset snapshots + relative ratios + risk ranking."""
    try:
        return service.get_cross_asset_signal_snapshot(estimator, window, as_of, min_periods)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/agreement", response_model=EstimatorAgreementResponse, summary="Estimator agreement + comparison panel")
def volatility_agreement(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    window: str = Query("5Y", description="Historical window for the panel percentiles."),
    min_periods: int = Query(126, ge=1, description="Min observations before a percentile is emitted."),
) -> EstimatorAgreementResponse:
    """Cross-estimator agreement (relative + absolute) and the per-estimator comparison panel."""
    try:
        return service.get_estimator_agreement(ticker.upper(), window, min_periods)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/derived", response_model=VolatilityRatioChangeResponse, summary="Term-ratio / change / dispersion line")
def volatility_derived(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    estimator: str = Query("rolling_20", description="Reference estimator key (drives the change view)."),
    view: str = Query("ratio", description="Derived view: ratio | change | dispersion."),
) -> VolatilityRatioChangeResponse:
    """20D/60D term ratio, relative volatility change, or estimator dispersion (Phase 2/4 chart views)."""
    try:
        return service.get_volatility_derived(ticker.upper(), estimator, view)
    except ValueError as exc:  # unknown estimator / view
        raise HTTPException(status_code=422, detail=str(exc))
