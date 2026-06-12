"""Backtest-results router (spec endpoints 2 + 3, Tabs 1 + 2).

Two cheap synchronous reads: the NAV comparison (scenario lines + dashed
benchmarks + summary) and the daily-returns scatter. ``scenario_ids`` is an
optional comma-separated filter (default all); ``benchmarks`` selects which B&H
overlays to draw.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas.backtest import BacktestDailyResponse, NavComparisonResponse, ReturnsResponse
from api.services import backtest_results as service

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
