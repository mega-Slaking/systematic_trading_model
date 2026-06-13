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

from api.schemas.common import NamedSeries, TableModel


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


class BacktestDailyResponse(BaseModel):
    """Endpoint 4 (Tab 3 raw table): one scenario's daily rows, paginated.

    ``table`` carries the requested columns (default: the scalar display set the
    Streamlit tab shows). ``total_rows`` is the unpaginated count for the scenario.
    """

    scenario_id: str
    total_rows: int
    offset: int
    limit: int | None
    table: TableModel


# --------------------------------------------------------------------------- #
# Returns Analysis diagnostic redesign
# (docs/returns_analysis_diagnostic_redesign_spec.md)
# --------------------------------------------------------------------------- #
class ScenarioMeta(BaseModel):
    """A scenario's readable label + parsed metadata, for the UI filters/picker.

    Shipped for *every* available scenario (not just the selected ones) so the
    family / volatility-method / target-vol filters and the multi-select can be
    populated without a second round-trip. Metadata fields are nullable: an
    unparseable id degrades gracefully rather than failing.
    """

    scenario_id: str
    scenario_label: str
    family: str | None
    lookback: int | None
    vol_method: str | None  # "roll" | "covlb" | "ewmacov" | None
    cov_lookback: int | None
    ewma_lambda: float | None
    target_vol: float | None  # decimal fraction (e.g. 0.03)


class ReturnsDiagnosticSeries(BaseModel):
    """One scenario's scatter points (date-range + return-filter scoped).

    Columnar (parallel arrays) to avoid per-point object allocation, mirroring
    ``ReturnsScatterSeries``. Intentionally lean -- date + return only -- so the
    full grid ships cheaply and legend toggles never refetch. Rich per-point
    context lives in the diagnostic tables and the on-demand click drilldown
    (``ReturnsPointDetail``), not in this array.
    """

    scenario_id: str
    scenario_label: str
    dates: list[str]
    returns: list[float | None]


class ReturnsDistributionSeries(BaseModel):
    """One scenario's full date-range return distribution (for the boxplot).

    Not restricted by the chart's return-filter mode -- a boxplot of only the
    outliers would be meaningless, so this always spans the selected date range.
    """

    scenario_id: str
    scenario_label: str
    returns: list[float | None]


class ReturnsPointDetail(BaseModel):
    """Rich diagnostic detail for a single (scenario, date) -- the click drilldown.

    Fetched on demand (one row) so the main scatter payload stays lean. ``lines``
    are the pre-formatted, missing-field-omitted diagnostic lines the panel renders.
    """

    scenario_id: str
    scenario_label: str
    date: str | None
    daily_return: float | None
    lines: list[str]


class ReturnsDiagnosticResponse(BaseModel):
    """The full Returns Analysis diagnostic payload (scatter + boxplot + tables).

    The entire scenario universe is shipped at once (``series`` / ``distribution``
    cover every scenario), so the page toggles curve visibility client-side via
    the Plotly legend with no further fetches. ``default_visible`` names the few
    scenarios drawn visible on first load; the rest start ``legendonly``.
    """

    available_scenarios: list[ScenarioMeta]  # every scenario, for filters/picker
    default_visible: list[str]  # scenario ids drawn visible on first load (~3)
    date_min: str | None  # data floor (ISO), for date-preset clamping
    date_max: str | None  # data ceiling (ISO); "Last 3 years" is relative to this
    filter_mode: str  # the return-filter actually applied to ``series``
    series: list[ReturnsDiagnosticSeries]  # the scatter, one per scenario (full grid)
    distribution: list[ReturnsDistributionSeries]  # boxplot input, per scenario
    worst: TableModel  # worst daily returns across the full scenario grid
    best: TableModel  # best daily returns across the full scenario grid
    dispersion: TableModel  # dates with the largest scenario dispersion
