"""Tearsheet schemas (spec endpoint 5, Tab 3) -- the one real compute path.

A faithful 1:1 serialization of ``accounting.tearsheet_models.TearsheetResult`` +
``TearsheetMetrics``: the metrics dataclass becomes a flat object, the curve
DataFrames become ``NamedSeries``, and the three summary DataFrames become
``TableModel`` (or ``null`` when the builder returns an empty frame, §6).

``TearsheetMetricsModel`` mirrors the 26-field ``TearsheetMetrics`` dataclass.
Every numeric field is nullable: ``tearsheet_calculator`` returns ``np.nan`` for
undefined stats (e.g. Calmar at zero drawdown), which the §6 boundary maps to
``null`` -- so these are ``float | None`` rather than the bare ``float`` of the
dataclass (``cost_drag`` is nullable there too).
"""

from __future__ import annotations

from pydantic import BaseModel

from api.schemas.common import NamedSeries, TableModel


class TearsheetMetricsModel(BaseModel):
    """Flat view of ``TearsheetMetrics`` (all 26 fields)."""

    scenario_id: str
    start_date: str
    end_date: str

    total_return: float | None
    cagr: float | None
    annualized_volatility: float | None
    sharpe: float | None
    sortino: float | None
    max_drawdown: float | None
    calmar: float | None

    var_95: float | None
    cvar_95: float | None
    worst_day: float | None
    best_day: float | None
    skew: float | None
    excess_kurtosis: float | None

    avg_turnover: float | None
    annualized_turnover: float | None
    total_cost: float | None
    cost_drag: float | None

    daily_hit_rate: float | None
    avg_win: float | None
    avg_loss: float | None
    payoff_ratio: float | None
    profit_factor: float | None
    parametric_var_95: float | None


class TearsheetResponse(BaseModel):
    """Full tearsheet: metrics + equity/drawdown/rolling curves + summary tables."""

    summary: TearsheetMetricsModel
    equity_curve: NamedSeries  # (date, nav)
    drawdown_curve: NamedSeries  # (date, drawdown)
    rolling_metrics: list[NamedSeries]  # rolling_volatility / rolling_return / rolling_sharpe
    exposure_summary: TableModel | None
    regime_summary: TableModel | None  # carries a regime_type column; the UI groups by it
    benchmark_summary: TableModel | None
    regime_match_rate: float | None  # fraction of rows that matched a regime row (the tab's caption)
