"""Backtest-results router (spec endpoints 2 + 3, Tabs 1 + 2).

Two cheap synchronous reads: the NAV comparison (scenario lines + dashed
benchmarks + summary) and the daily-returns scatter. ``scenario_ids`` is an
optional comma-separated filter (default all); ``benchmarks`` selects which B&H
overlays to draw.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import ORJSONResponse

from api.schemas.backtest import (
    BacktestDailyResponse,
    NavComparisonResponse,
    ReturnsDiagnosticResponse,
    ReturnsPointDetail,
    ReturnsResponse,
)
from api.services import backtest_results as service
from api.services import returns_diagnostics

router = APIRouter(prefix="/backtest-results", tags=["backtest-results"])

_SCENARIO_IDS_QUERY = Query(
    default=None,
    description="Comma-separated scenario ids (case-sensitive). Omit for all.",
)
_BENCHMARKS_QUERY = Query(
    default=None,
    description="Comma-separated benchmark tickers (TLT,AGG,SHY). Omit for all three.",
)


def _split_csv(value: str | None, *, upper: bool = False) -> list[str] | None:
    """Split a comma-separated query param into a clean list (or None)."""
    if not value:
        return None
    parts = [p.strip().upper() if upper else p.strip() for p in value.split(",") if p.strip()]
    return parts or None


@router.get("/nav-comparison", response_model=NavComparisonResponse, summary="NAV comparison + summary")
def nav_comparison(
    scenario_ids: str | None = _SCENARIO_IDS_QUERY,
    benchmarks: str | None = _BENCHMARKS_QUERY,
) -> NavComparisonResponse:
    """Per-scenario NAV lines, dashed B&H benchmarks, and the summary table (Tab 1)."""
    return service.get_nav_comparison(
        _split_csv(scenario_ids),
        _split_csv(benchmarks, upper=True),
    )


@router.get("/returns", response_model=ReturnsResponse, summary="Daily returns scatter")
def returns(scenario_ids: str | None = _SCENARIO_IDS_QUERY) -> ReturnsResponse:
    """Columnar daily-return series per scenario for the WebGL scatter (Tab 2)."""
    return service.get_returns(_split_csv(scenario_ids))


@router.get(
    "/returns-diagnostic",
    response_model=ReturnsDiagnosticResponse,
    summary="Returns Analysis diagnostic payload",
)
def returns_diagnostic(
    scenario_ids: str | None = _SCENARIO_IDS_QUERY,
    start: str | None = Query(None, description="ISO start date (clipped to data range)."),
    end: str | None = Query(None, description="ISO end date (clipped to data range)."),
    filter_mode: str = Query(
        "all",
        description="Return-filter for the scatter: all | abs_gt_1pct | abs_gt_2pct "
        "| worst_1pct | best_1pct | extremes_20.",
    ),
    table_limit: int = Query(20, ge=1, le=200, description="Rows per diagnostic table."),
) -> ReturnsDiagnosticResponse:
    """Enriched per-scenario scatter + boxplot distribution + worst/best/dispersion
    tables for the redesigned Returns Analysis view. Ships every scenario at once
    so the page toggles curve visibility client-side (no refetch).

    Returns an ``ORJSONResponse`` directly: the service builds the (large) payload
    as a plain dict and we skip Pydantic response validation for speed
    (``response_model`` above still drives the OpenAPI schema)."""
    return ORJSONResponse(
        content=returns_diagnostics.get_returns_diagnostic(
            scenario_ids=_split_csv(scenario_ids),
            start=start,
            end=end,
            filter_mode=filter_mode,
            table_limit=table_limit,
        )
    )


@router.get(
    "/returns-diagnostic/point",
    response_model=ReturnsPointDetail,
    summary="Single-point diagnostic detail (click drilldown)",
)
def returns_diagnostic_point(
    scenario_id: str = Query(..., description="Scenario id of the clicked point."),
    date: str = Query(..., description="ISO date of the clicked point."),
) -> ReturnsPointDetail:
    """Rich per-point context for the Returns Analysis click drilldown (one row)."""
    try:
        return returns_diagnostics.get_returns_point_detail(scenario_id, date)
    except LookupError:
        raise HTTPException(
            status_code=404, detail=f"No observation for '{scenario_id}' on {date}"
        )


@router.get("/{scenario_id}/daily", response_model=BacktestDailyResponse, summary="Daily rows for a scenario")
def daily(
    scenario_id: str,
    columns: str | None = Query(None, description="Comma-separated column subset. Default: scalar display set."),
    limit: int | None = Query(None, ge=1, description="Max rows to return (pagination)."),
    offset: int = Query(0, ge=0, description="Row offset (pagination)."),
) -> BacktestDailyResponse:
    """Raw daily rows for one scenario (Tab 3 table)."""
    try:
        return service.get_daily_rows(scenario_id, _split_csv(columns), limit, offset)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
