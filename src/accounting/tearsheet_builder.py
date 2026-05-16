import numpy as np
import pandas as pd

from accounting.tearsheet_models import TearsheetMetrics, TearsheetResult
from accounting.tearsheet_calculator import (
    build_benchmark_summary,
    build_exposure_summary,
    build_regime_summary,
    compute_annualized_turnover,
    compute_annualized_volatility,
    compute_avg_turnover,
    compute_avg_win,
    compute_avg_loss,
    compute_best_day,
    compute_cagr,
    compute_calmar,
    compute_cost_drag,
    compute_cvar,
    compute_daily_hit_rate,
    compute_drawdown_curve,
    compute_excess_kurtosis,
    compute_max_drawdown,
    compute_payoff_ratio,
    compute_profit_factor,
    compute_parametric_var,
    compute_rolling_metrics,
    compute_sharpe,
    compute_skew,
    compute_sortino,
    compute_total_cost,
    compute_total_return,
    compute_var,
    compute_worst_day,
)


def build_tearsheet(
    results_df: pd.DataFrame,
    regime_df: pd.DataFrame | None = None,
    benchmark_prices_df: pd.DataFrame | None = None,
    risk_free_rate: float = 0.02, #question this value
    periods_per_year: int = 252,
) -> TearsheetResult:
    df = _prepare_results_df(results_df)

    scenario_id = _get_scenario_id(df)
    returns = _get_returns(df)

    equity_curve = _build_equity_curve(df)
    drawdown_curve = compute_drawdown_curve(equity_curve)

    summary = _build_summary_metrics(
        scenario_id=scenario_id,
        df=df,
        returns=returns,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        risk_free_rate=risk_free_rate,
        periods_per_year=periods_per_year,
    )

    rolling_metrics = compute_rolling_metrics(
        df=df,
        returns=returns,
        periods_per_year=periods_per_year,
    )

    return TearsheetResult(
        summary=summary,
        equity_curve=equity_curve,
        drawdown_curve=drawdown_curve,
        rolling_metrics=rolling_metrics,
        exposure_summary=build_exposure_summary(df),
        regime_summary=build_regime_summary(
            results_df=df,
            regime_df=regime_df,
            periods_per_year=periods_per_year,
        ),
        benchmark_summary=build_benchmark_summary(
            results_df=df,
            benchmark_prices_df=benchmark_prices_df,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
        ),
    )


def _build_summary_metrics(
    scenario_id: str,
    df: pd.DataFrame,
    returns: pd.Series,
    equity_curve: pd.DataFrame,
    drawdown_curve: pd.DataFrame,
    risk_free_rate: float,
    periods_per_year: int,
) -> TearsheetMetrics:
    start_date = str(equity_curve["date"].iloc[0].date())
    end_date = str(equity_curve["date"].iloc[-1].date())

    total_return = compute_total_return(equity_curve)
    n_periods = len(returns)

    cagr = compute_cagr(
        total_return=total_return,
        n_periods=n_periods,
        periods_per_year=periods_per_year,
    )

    annualized_volatility = compute_annualized_volatility(
        returns=returns,
        periods_per_year=periods_per_year,
    )

    sharpe = compute_sharpe(
        returns=returns,
        risk_free_rate=risk_free_rate,
        periods_per_year=periods_per_year,
    )

    sortino = compute_sortino(
        returns=returns,
        risk_free_rate=risk_free_rate,
        periods_per_year=periods_per_year,
    )

    max_drawdown = compute_max_drawdown(drawdown_curve)

    avg_turnover = compute_avg_turnover(df)

    return TearsheetMetrics(
        scenario_id=scenario_id,
        start_date=start_date,
        end_date=end_date,
        total_return=total_return,
        cagr=cagr,
        annualized_volatility=annualized_volatility,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_drawdown,
        calmar=compute_calmar(cagr, max_drawdown),
        var_95=compute_var(returns, confidence=0.95),
        cvar_95=compute_cvar(returns, confidence=0.95),
        worst_day=compute_worst_day(returns),
        best_day=compute_best_day(returns),
        skew=compute_skew(returns),
        excess_kurtosis=compute_excess_kurtosis(returns),
        avg_turnover=avg_turnover,
        annualized_turnover=compute_annualized_turnover(
            avg_turnover=avg_turnover,
            periods_per_year=periods_per_year,
        ),
        total_cost=compute_total_cost(df),
        cost_drag=compute_cost_drag(
            df=df,
            net_total_return=total_return,
            n_periods=n_periods,
            periods_per_year=periods_per_year,
        ),
        parametric_var_95=compute_parametric_var(
            returns=returns,
            confidence=0.95,
        ),
        daily_hit_rate=compute_daily_hit_rate(returns),
        avg_win=compute_avg_win(returns),
        avg_loss=compute_avg_loss(returns),
        payoff_ratio=compute_payoff_ratio(returns),
        profit_factor=compute_profit_factor(returns),
    )


def _prepare_results_df(results_df: pd.DataFrame) -> pd.DataFrame:
    if results_df.empty:
        raise ValueError("Cannot build tearsheet from empty results dataframe.")

    required_columns = {"date", "scenario_id", "nav"}
    missing_columns = required_columns - set(results_df.columns)

    if missing_columns:
        raise ValueError(
            f"Results dataframe is missing required columns: {sorted(missing_columns)}"
        )

    df = results_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    return df


def _get_scenario_id(df: pd.DataFrame) -> str:
    scenario_ids = df["scenario_id"].dropna().unique()

    if len(scenario_ids) == 0:
        return "unknown"

    if len(scenario_ids) > 1:
        raise ValueError(
            "Tearsheet builder expects one scenario_id at a time. "
            f"Received: {scenario_ids.tolist()}"
        )

    return str(scenario_ids[0])


def _get_returns(df: pd.DataFrame) -> pd.Series:
    if "ret" in df.columns:
        returns = df["ret"].astype(float)
    elif "daily_return" in df.columns:
        returns = df["daily_return"].astype(float)
    elif "return" in df.columns:
        returns = df["return"].astype(float)
    else:
        returns = df["nav"].astype(float).pct_change()

    return returns.replace([np.inf, -np.inf], np.nan).dropna()


def _build_equity_curve(df: pd.DataFrame) -> pd.DataFrame:
    equity = df[["date", "nav"]].copy()
    equity["nav"] = equity["nav"].astype(float)

    return equity