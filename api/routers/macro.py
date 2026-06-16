"""Macro router (spec endpoints 10 + 11, Page 6)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas.macro import (
    ConditionalReturnsResponse,
    ForwardReturnScatterResponse,
    MacroResponse,
    MacroSnapshotResponse,
    RegimeTimelineResponse,
    YieldCurveResponse,
)
from api.services import macro as service

router = APIRouter(prefix="/macro", tags=["macro"])


def _split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    return parts or None


@router.get("", response_model=MacroResponse, summary="Macro indicator series")
def macro(
    indicators: str | None = Query(
        None,
        description="Comma-separated indicator keys (raw or derived, e.g. cpi_yoy, real_policy_rate). Default: all.",
    ),
) -> MacroResponse:
    """One series per requested macro indicator (each on its own date axis)."""
    return service.get_macro(_split_csv(indicators))


@router.get("/yield-curve", response_model=YieldCurveResponse, summary="10Y/2Y yields + spread")
def yield_curve() -> YieldCurveResponse:
    """10Y and 2Y yields plus the 10Y-2Y spread."""
    return service.get_yield_curve()


@router.get("/snapshot", response_model=MacroSnapshotResponse, summary="Latest macro snapshot cards")
def snapshot() -> MacroSnapshotResponse:
    """Latest reading of each headline indicator (per-card observation dates)."""
    return service.get_macro_snapshot()


@router.get("/regime-timeline", response_model=RegimeTimelineResponse, summary="Macro-regime timeline")
def regime_timeline() -> RegimeTimelineResponse:
    """Dashboard macro-regime over time + optional engine duration-support overlay."""
    return service.get_regime_timeline()


@router.get("/conditional-returns", response_model=ConditionalReturnsResponse, summary="Forward returns by regime")
def conditional_returns(
    etf: str | None = Query(None, description="Restrict to one ETF (TLT/AGG/SHY). Default: all."),
    min_observations: int = Query(12, ge=1, description="Below this observation count a regime row is flagged 'thin'."),
) -> ConditionalReturnsResponse:
    """Regime × ETF forward-return statistics (descriptive; see response notes)."""
    return service.get_conditional_returns(etf=etf, min_observations=min_observations)


@router.get("/forward-return-scatter", response_model=ForwardReturnScatterResponse, summary="Macro vs forward-return scatter")
def forward_return_scatter(
    etf: str = Query("TLT", description="ETF whose forward return is the Y axis (TLT/AGG/SHY)."),
    indicator: str = Query("cpi_yoy_change_3m", description="Macro indicator key for the X axis."),
    horizon: str = Query("3m", description="Forward horizon: 1m / 3m / 6m / 12m."),
) -> ForwardReturnScatterResponse:
    """(macro reading, subsequent ETF return) points for the explorer scatter mode."""
    try:
        return service.get_forward_return_scatter(etf=etf, indicator=indicator, horizon=horizon)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
