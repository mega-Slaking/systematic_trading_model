"""Backtest-results schemas (spec endpoints 2 + 3, Tabs 1 + 2).

Endpoint 2 (``/backtest-results/nav-comparison``) bundles the per-scenario NAV
lines, the dashed buy-and-hold benchmark lines, and the performance-summary table
that Streamlit computed inline (``nav_comparison.py``), moved server-side per
§2.4.4. Endpoint 3 (``/backtest-results/returns``) ships the dense daily-return
scatter in the **columnar** form (§4.4) to trim JSON size for the WebGL plot.

Floats are nullable throughout: the §6 boundary maps NaN/Inf to ``null`` (e.g. a
degenerate zero-NAV base), so the summary fields are ``float | None`` rather than
the bare ``float`` sketched in §4.4 -- consistent with the codebase's §6 rule.
"""

from __future__ import annotations

from pydantic import BaseModel

from api.schemas.common import NamedSeries


class ScenarioSummaryRow(BaseModel):
    """One row of the "Scenario Performance Summary" table (Tab 1)."""

    scenario_id: str
    final_nav: float | None
    total_return: float | None  # decimal fraction
    max_drawdown: float | None  # decimal fraction (<= 0)
    annualized_volatility: float | None  # ret.std() * sqrt(252); None if 'ret' absent


class NavComparisonResponse(BaseModel):
    """Tab 1: scenario NAV lines + dashed B&H benchmark lines + summary table."""

    start_date: str | None  # backtest window floor = min(date); ISO YYYY-MM-DD
    initial_nav: float  # first scenario's starting NAV, used to scale the benchmarks
    scenario_series: list[NamedSeries]  # one per scenario, name "Scenario: <id>"
    benchmark_series: list[NamedSeries]  # dashed B&H lines, meta={"dash": "dash"}
    summary: list[ScenarioSummaryRow]


class ReturnsScatterSeries(BaseModel):
    """Daily returns for one scenario, columnar (parallel ``dates``/``returns``)."""

    scenario_id: str
    dates: list[str]
    returns: list[float | None]


class ReturnsResponse(BaseModel):
    """Tab 2: one columnar return series per scenario (rendered via Plotly WebGL)."""

    series: list[ReturnsScatterSeries]
