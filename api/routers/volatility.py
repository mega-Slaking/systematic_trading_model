"""Volatility-features router (spec endpoints 8 + 9, Tab 5)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas.volatility import (
    EstimatorAgreementResponse,
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
