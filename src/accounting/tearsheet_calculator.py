import ast
import json
import numpy as np
import pandas as pd

from src.universe import UNIVERSE


def compute_total_return(equity_curve: pd.DataFrame) -> float:
    start_nav = float(equity_curve["nav"].iloc[0])
    end_nav = float(equity_curve["nav"].iloc[-1])

    return end_nav / start_nav - 1.0


def compute_cagr(
    total_return: float,
    n_periods: int,
    periods_per_year: int,
) -> float:
    if n_periods <= 0:
        return np.nan

    return (1.0 + total_return) ** (periods_per_year / n_periods) - 1.0


def compute_annualized_volatility(
    returns: pd.Series,
    periods_per_year: int,
) -> float:
    return float(returns.std(ddof=1) * np.sqrt(periods_per_year))


def compute_sharpe(
    returns: pd.Series,
    risk_free_rate: float,
    periods_per_year: int,
) -> float:
    rf_daily = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    excess_returns = returns - rf_daily

    annualized_volatility = compute_annualized_volatility(
        returns=returns,
        periods_per_year=periods_per_year,
    )

    return safe_divide(
        excess_returns.mean() * periods_per_year,
        annualized_volatility,
    )


def compute_sortino(
    returns: pd.Series,
    risk_free_rate: float,
    periods_per_year: int,
) -> float:
    rf_daily = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0
    excess_returns = returns - rf_daily

    downside_returns = np.minimum(excess_returns, 0.0)
    downside_deviation = (
        np.sqrt(np.mean(downside_returns**2)) * np.sqrt(periods_per_year)
    )

    return safe_divide(
        excess_returns.mean() * periods_per_year,
        downside_deviation,
    )


def compute_drawdown_curve(equity_curve: pd.DataFrame) -> pd.DataFrame:
    curve = equity_curve.copy()
    curve["running_peak"] = curve["nav"].cummax()
    curve["drawdown"] = curve["nav"] / curve["running_peak"] - 1.0

    return curve[["date", "drawdown"]]


def compute_max_drawdown(drawdown_curve: pd.DataFrame) -> float:
    return float(drawdown_curve["drawdown"].min())


def compute_calmar(cagr: float, max_drawdown: float) -> float:
    return safe_divide(cagr, abs(max_drawdown))


def compute_var(
    returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    quantile = 1.0 - confidence
    var_threshold = returns.quantile(quantile)

    return -float(var_threshold)


def compute_cvar(
    returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    quantile = 1.0 - confidence
    var_threshold = returns.quantile(quantile)

    tail_returns = returns[returns <= var_threshold]

    if tail_returns.empty:
        return np.nan

    return -float(tail_returns.mean())


def compute_skew(returns: pd.Series) -> float:
    return float(returns.skew())


def compute_excess_kurtosis(returns: pd.Series) -> float:
    return float(returns.kurtosis())


def compute_avg_turnover(df: pd.DataFrame) -> float:
    return get_column_mean(df, "turnover")


def compute_annualized_turnover(
    avg_turnover: float,
    periods_per_year: int,
) -> float:
    return avg_turnover * periods_per_year


def compute_total_cost(df: pd.DataFrame) -> float:
    if "total_cost" in df.columns:
        return float(df["total_cost"].sum())

    total = 0.0

    if "fee_cost" in df.columns:
        total += float(df["fee_cost"].sum())

    if "slippage_cost" in df.columns:
        total += float(df["slippage_cost"].sum())

    return total


def compute_cost_drag(
    df: pd.DataFrame,
    net_total_return: float,
    n_periods: int,
    periods_per_year: int,
) -> float | None:
    if "gross_daily_return" not in df.columns:
        return None

    gross_returns = df["gross_daily_return"].astype(float).dropna()

    if gross_returns.empty:
        return None

    gross_total_return = (1.0 + gross_returns).prod() - 1.0
    gross_cagr = compute_cagr(gross_total_return, n_periods, periods_per_year)
    net_cagr = compute_cagr(net_total_return, n_periods, periods_per_year)

    return gross_cagr - net_cagr


def compute_rolling_metrics(
    df: pd.DataFrame,
    returns: pd.Series,
    periods_per_year: int,
    window: int = 252,
) -> pd.DataFrame:
    rolling_return = (1.0 + returns).rolling(window).apply(np.prod, raw=True) - 1.0
    rolling_volatility = returns.rolling(window).std() * np.sqrt(periods_per_year)

    rolling_sharpe = safe_series_divide(
        returns.rolling(window).mean() * periods_per_year,
        rolling_volatility,
    )

    return pd.DataFrame(
        {
            "date": df.loc[returns.index, "date"].values,
            "rolling_return": rolling_return.values,
            "rolling_volatility": rolling_volatility.values,
            "rolling_sharpe": rolling_sharpe.values,
        }
    )


def compute_worst_day(returns: pd.Series) -> float:
    if returns.empty:
        return np.nan

    return float(returns.min())


def compute_best_day(returns: pd.Series) -> float:
    if returns.empty:
        return np.nan

    return float(returns.max())


def parse_weights(value: object) -> dict[str, float]:
    if isinstance(value, dict):
        return {str(k): float(v) for k, v in value.items()}

    if value is None or pd.isna(value):
        return {}

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return {}

        try:
            parsed = json.loads(value)
            return {str(k): float(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            pass

        try:
            parsed = ast.literal_eval(value)
            return {str(k): float(v) for k, v in parsed.items()}
        except (ValueError, SyntaxError):
            return {}

    return {}


def build_weight_frame(
    df: pd.DataFrame,
    assets: tuple[str, ...] = ("TLT", "AGG", "SHY"),
) -> pd.DataFrame:
    if "weights" not in df.columns:
        return pd.DataFrame()

    rows = []

    for _, row in df.iterrows():
        weights = parse_weights(row["weights"])

        output_row = {
            "date": row["date"],
            "scenario_id": row.get("scenario_id"),
        }

        for asset in assets:
            output_row[asset] = float(weights.get(asset, 0.0))

        rows.append(output_row)

    return pd.DataFrame(rows)


def build_exposure_summary(
    df: pd.DataFrame,
    assets: tuple[str, ...] = ("TLT", "AGG", "SHY"),
    defensive_asset: str = "SHY",
    duration_assets: tuple[str, ...] = ("TLT", "AGG"),
    mostly_threshold: float = 0.50,
) -> pd.DataFrame:
    weight_frame = build_weight_frame(df, assets=assets)

    if weight_frame.empty:
        return pd.DataFrame()

    asset_weight_cols = list(assets)

    weight_frame["max_asset_concentration"] = (
        weight_frame[asset_weight_cols].abs().max(axis=1)
    )

    weight_frame["duration_exposure"] = (
        weight_frame[list(duration_assets)].sum(axis=1)
    )

    weight_frame["defensive_exposure"] = weight_frame[defensive_asset]

    metrics = []

    for asset in assets:
        metrics.append(
            {
                "metric": f"avg_weight_{asset}",
                "value": float(weight_frame[asset].mean()),
            }
        )

    metrics.extend(
        [
            {
                "metric": "avg_max_asset_concentration",
                "value": float(weight_frame["max_asset_concentration"].mean()),
            },
            {
                "metric": "max_asset_concentration",
                "value": float(weight_frame["max_asset_concentration"].max()),
            },
            {
                "metric": "time_mostly_defensive",
                "value": float(
                    (weight_frame["defensive_exposure"] >= mostly_threshold).mean()
                ),
            },
            {
                "metric": "time_mostly_duration_exposed",
                "value": float(
                    (weight_frame["duration_exposure"] >= mostly_threshold).mean()
                ),
            },
            {
                "metric": "avg_duration_exposure",
                "value": float(weight_frame["duration_exposure"].mean()),
            },
            {
                "metric": "avg_defensive_exposure",
                "value": float(weight_frame["defensive_exposure"].mean()),
            },
        ]
    )

    return pd.DataFrame(metrics)


def merge_regime_trace(
    results_df: pd.DataFrame,
    regime_df: pd.DataFrame,
) -> pd.DataFrame:
    results = results_df.copy()
    regimes = regime_df.copy()

    results["date"] = pd.to_datetime(results["date"])
    regimes["date"] = pd.to_datetime(regimes["date"])

    merge_cols = ["date"]

    if "scenario_id" in results.columns and "scenario_id" in regimes.columns:
        merge_cols.append("scenario_id")

    return results.merge(
        regimes,
        on=merge_cols,
        how="left",
    )


def build_regime_summary(
    results_df: pd.DataFrame,
    regime_df: pd.DataFrame | None,
    periods_per_year: int,
) -> pd.DataFrame:
    if regime_df is None or regime_df.empty:
        return pd.DataFrame()

    if "date" not in regime_df.columns:
        return pd.DataFrame()

    merged = merge_regime_trace(
        results_df=results_df,
        regime_df=regime_df,
    )

    if merged.empty:
        return pd.DataFrame()

    weight_frame = build_weight_frame(merged)

    if not weight_frame.empty:
        merged = merged.merge(
            weight_frame,
            on=["date", "scenario_id"],
            how="left",
        )

    regime_columns = [
        "inflation_regime",
        "growth_regime",
        "labour_regime",
        "curve_state",
        "macro_supports_duration",
    ]

    summaries = []

    for regime_column in regime_columns:
        if regime_column not in merged.columns:
            continue

        grouped = merged.dropna(subset=[regime_column]).groupby(regime_column)

        for regime_name, group in grouped:
            group = group.sort_values("date")

            returns = _extract_returns_from_group(group)

            if returns.empty:
                continue

            equity_curve = pd.DataFrame(
                {
                    "date": group.loc[returns.index, "date"].values,
                    "nav": group.loc[returns.index, "nav"].astype(float).values,
                }
            )

            drawdown_curve = compute_drawdown_curve(equity_curve)

            row = {
                "regime_type": regime_column,
                "regime": regime_name,
                "n_days": int(len(returns)),
                "total_return": float((1.0 + returns).prod() - 1.0),
                "annualized_volatility": compute_annualized_volatility(
                    returns=returns,
                    periods_per_year=periods_per_year,
                ),
                "max_drawdown": compute_max_drawdown(drawdown_curve),
                "worst_day": compute_worst_day(returns),
                "best_day": compute_best_day(returns),
            }

            for asset in UNIVERSE:
                if asset in group.columns:
                    row[f"avg_weight_{asset}"] = float(group[asset].mean())

            summaries.append(row)

    return pd.DataFrame(summaries)


def build_benchmark_summary(
    results_df: pd.DataFrame,
    benchmark_prices_df: pd.DataFrame | None,
    periods_per_year: int,
    risk_free_rate: float = 0.02,
    benchmark_tickers: tuple[str, ...] = ("TLT", "AGG", "SHY"),
) -> pd.DataFrame:
    if benchmark_prices_df is None or benchmark_prices_df.empty:
        return pd.DataFrame()

    if not {"date", "ticker", "close"}.issubset(benchmark_prices_df.columns):
        return pd.DataFrame()

    strategy_returns = _extract_returns_from_group(results_df)

    if strategy_returns.empty:
        return pd.DataFrame()

    strategy_frame = pd.DataFrame(
        {
            "date": results_df.loc[strategy_returns.index, "date"].values,
            "strategy_return": strategy_returns.values,
        }
    )

    benchmark_returns = build_benchmark_returns(
        benchmark_prices_df=benchmark_prices_df,
        start_date=strategy_frame["date"].min(),
        end_date=strategy_frame["date"].max(),
        benchmark_tickers=benchmark_tickers,
    )

    if benchmark_returns.empty:
        return pd.DataFrame()

    summaries = []

    for benchmark_name in benchmark_returns.columns:
        combined = strategy_frame.merge(
            benchmark_returns[[benchmark_name]].reset_index(),
            on="date",
            how="inner",
        ).dropna()

        if combined.empty:
            continue

        s_ret = combined["strategy_return"].astype(float)
        b_ret = combined[benchmark_name].astype(float)

        benchmark_total_return = float((1.0 + b_ret).prod() - 1.0)
        strategy_total_return = float((1.0 + s_ret).prod() - 1.0)

        n_periods = len(combined)

        benchmark_cagr = compute_cagr(
            total_return=benchmark_total_return,
            n_periods=n_periods,
            periods_per_year=periods_per_year,
        )

        strategy_cagr = compute_cagr(
            total_return=strategy_total_return,
            n_periods=n_periods,
            periods_per_year=periods_per_year,
        )

        benchmark_equity = pd.DataFrame(
            {
                "date": combined["date"].values,
                "nav": (1.0 + b_ret).cumprod(),
            }
        )

        benchmark_drawdown = compute_drawdown_curve(benchmark_equity)
        benchmark_max_drawdown = compute_max_drawdown(benchmark_drawdown)

        tracking_error = compute_tracking_error(
            strategy_returns=s_ret,
            benchmark_returns=b_ret,
            periods_per_year=periods_per_year,
        )

        active_cagr = strategy_cagr - benchmark_cagr

        summaries.append(
            {
                "benchmark": benchmark_name,
                "benchmark_total_return": benchmark_total_return,
                "benchmark_cagr": benchmark_cagr,
                "benchmark_volatility": compute_annualized_volatility(
                    returns=b_ret,
                    periods_per_year=periods_per_year,
                ),
                "benchmark_max_drawdown": benchmark_max_drawdown,
                "active_cagr": active_cagr,
                "tracking_error": tracking_error,
                "information_ratio": compute_information_ratio(
                    strategy_returns=s_ret,
                    benchmark_returns=b_ret,
                    tracking_error=tracking_error,
                    periods_per_year=periods_per_year,
                ),
                "beta": compute_beta(
                    strategy_returns=s_ret,
                    benchmark_returns=b_ret,
                    risk_free_rate=risk_free_rate,
                    periods_per_year=periods_per_year,
                ),
                "alpha": compute_alpha(
                    strategy_returns=s_ret,
                    benchmark_returns=b_ret,
                    risk_free_rate=risk_free_rate,
                    periods_per_year=periods_per_year,
                ),
                "correlation": compute_correlation(
                    strategy_returns=s_ret,
                    benchmark_returns=b_ret,
                ),
                "r_squared": compute_r_squared(
                    strategy_returns=s_ret,
                    benchmark_returns=b_ret,
                ),
            }
        )

    return pd.DataFrame(summaries)


def _extract_returns_from_group(group: pd.DataFrame) -> pd.Series:
    if "ret" in group.columns:
        returns = group["ret"].astype(float)
    elif "daily_return" in group.columns:
        returns = group["daily_return"].astype(float)
    elif "return" in group.columns:
        returns = group["return"].astype(float)
    else:
        returns = group["nav"].astype(float).pct_change()

    return returns.replace([np.inf, -np.inf], np.nan).dropna()


def get_column_mean(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns:
        return np.nan

    return float(df[column].mean())


def safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0 or np.isnan(denominator):
        return np.nan

    return float(numerator / denominator)


def safe_series_divide(
    numerator: pd.Series,
    denominator: pd.Series,
) -> pd.Series:
    denominator = denominator.replace(0, np.nan)
    return numerator / denominator


def build_benchmark_returns(
    benchmark_prices_df: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    benchmark_tickers: tuple[str, ...] = ("TLT", "AGG", "SHY"),
) -> pd.DataFrame:
    prices = benchmark_prices_df.copy()
    prices["date"] = pd.to_datetime(prices["date"])

    prices = prices[
        (prices["ticker"].isin(benchmark_tickers))
        & (prices["date"] >= start_date)
        & (prices["date"] <= end_date)
    ]

    if prices.empty:
        return pd.DataFrame()

    price_wide = (
        prices.pivot(index="date", columns="ticker", values="close")
        .sort_index()
        .ffill()
    )

    returns = price_wide.pct_change().dropna()

    available_tickers = [
        ticker for ticker in benchmark_tickers if ticker in returns.columns
    ]

    benchmark_returns = returns[available_tickers].copy()

    if available_tickers:
        benchmark_returns["EqualWeight_TLT_AGG_SHY"] = (
            benchmark_returns[available_tickers].mean(axis=1)
        )

    return benchmark_returns


def compute_beta(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float,
    periods_per_year: int,
) -> float:
    rf_daily = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0

    strategy_excess = strategy_returns - rf_daily
    benchmark_excess = benchmark_returns - rf_daily

    benchmark_variance = benchmark_excess.var(ddof=1)

    if benchmark_variance == 0 or pd.isna(benchmark_variance):
        return np.nan

    return float(strategy_excess.cov(benchmark_excess) / benchmark_variance)


def compute_alpha(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float,
    periods_per_year: int,
) -> float:
    rf_daily = (1.0 + risk_free_rate) ** (1.0 / periods_per_year) - 1.0

    beta = compute_beta(
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        risk_free_rate=risk_free_rate,
        periods_per_year=periods_per_year,
    )

    if pd.isna(beta):
        return np.nan

    strategy_excess = strategy_returns - rf_daily
    benchmark_excess = benchmark_returns - rf_daily

    alpha_daily = strategy_excess.mean() - beta * benchmark_excess.mean()

    return float((1.0 + alpha_daily) ** periods_per_year - 1.0)


def compute_tracking_error(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int,
) -> float:
    active_returns = strategy_returns - benchmark_returns

    return float(active_returns.std(ddof=1) * np.sqrt(periods_per_year))


def compute_information_ratio(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    tracking_error: float,
    periods_per_year: int,
) -> float:
    active_returns = strategy_returns - benchmark_returns
    annualized_active_return = active_returns.mean() * periods_per_year

    return safe_divide(annualized_active_return, tracking_error)


def compute_correlation(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> float:
    return float(strategy_returns.corr(benchmark_returns))


def compute_r_squared(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> float:
    correlation = compute_correlation(
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
    )

    if pd.isna(correlation):
        return np.nan

    return float(correlation**2)


def compute_daily_hit_rate(returns: pd.Series) -> float:
    returns = returns.dropna()

    if returns.empty:
        return np.nan

    return float((returns > 0).mean())


def compute_avg_win(returns: pd.Series) -> float:
    wins = returns[returns > 0]

    if wins.empty:
        return np.nan

    return float(wins.mean())


def compute_avg_loss(returns: pd.Series) -> float:
    losses = returns[returns < 0]

    if losses.empty:
        return np.nan

    return float(abs(losses.mean()))


def compute_payoff_ratio(returns: pd.Series) -> float:
    avg_win = compute_avg_win(returns)
    avg_loss = compute_avg_loss(returns)

    return safe_divide(avg_win, avg_loss)


def compute_profit_factor(returns: pd.Series) -> float:
    wins = returns[returns > 0]
    losses = returns[returns < 0]

    total_wins = wins.sum()
    total_losses = abs(losses.sum())

    return safe_divide(total_wins, total_losses)


def compute_parametric_var(
    returns: pd.Series,
    confidence: float = 0.95,
) -> float:
    returns = returns.dropna()

    if returns.empty:
        return np.nan

    z_scores = {
        0.90: -1.2815515655446004,
        0.95: -1.6448536269514722,
        0.99: -2.3263478740408408,
    }

    z_score = z_scores.get(confidence)

    if z_score is None:
        raise ValueError(
            f"Unsupported confidence level: {confidence}. "
            "Supported values are 0.90, 0.95, and 0.99."
        )

    mean_return = returns.mean()
    volatility = returns.std(ddof=1)

    return -float(mean_return + z_score * volatility)