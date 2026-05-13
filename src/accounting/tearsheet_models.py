from dataclasses import dataclass
import pandas as pd


@dataclass(frozen=True)
class TearsheetMetrics:
    scenario_id: str
    start_date: str
    end_date: str

    total_return: float
    cagr: float
    annualized_volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float

    var_95: float
    cvar_95: float
    worst_day: float
    best_day: float
    skew: float
    excess_kurtosis: float

    avg_turnover: float
    annualized_turnover: float
    total_cost: float
    cost_drag: float | None


@dataclass
class TearsheetResult:
    summary: TearsheetMetrics
    equity_curve: pd.DataFrame
    drawdown_curve: pd.DataFrame
    rolling_metrics: pd.DataFrame
    exposure_summary: pd.DataFrame | None
    regime_summary: pd.DataFrame | None