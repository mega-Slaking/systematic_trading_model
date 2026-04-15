import pandas as pd
import numpy as np
from typing import Dict

from src.covariance.models import (
    CovarianceConfig,
    CovarianceEstimate,
    CovarianceRequest,
)


def estimate_covariance(
    request: CovarianceRequest,
    config: CovarianceConfig | None = None,
) -> CovarianceEstimate:
    config = config or CovarianceConfig()

    if config.method == "sample_cov":
        return _estimate_sample_cov(request, config)

    if config.method == "ewma_cov":
        return _estimate_ewma_cov(request, config)

    raise ValueError(f"Unsupported covariance method: {config.method}")


def _estimate_sample_cov(
    request: CovarianceRequest,
    config: CovarianceConfig,
) -> CovarianceEstimate:
    df = request.etf_history.copy()

    required_columns = {"date", "ticker", "close"}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(
            f"ETF history is missing required columns: {sorted(missing_columns)}"
        )

    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    as_of_date = pd.Timestamp(request.as_of_date).tz_localize(None)

    df = df[df["date"] < as_of_date].copy()

    if df.empty:
        return CovarianceEstimate(
            method="sample_cov",
            as_of_date=pd.Timestamp(request.as_of_date),
            annualized=True,
            tickers=[],
            covariance_matrix=pd.DataFrame(),
            notes=["No ETF history available before as_of_date."],
            invalid_tickers=list(request.tickers),
        )

    df = df.sort_values(["ticker", "date"]).copy()
    df["return"] = df.groupby("ticker")["close"].pct_change()

    returns_wide = df.pivot(index="date", columns="ticker", values="return")

    requested_tickers = list(request.tickers)
    available_tickers = [ticker for ticker in requested_tickers if ticker in returns_wide.columns]
    invalid_tickers = [ticker for ticker in requested_tickers if ticker not in returns_wide.columns]

    notes: list[str] = []

    if not available_tickers:
        return CovarianceEstimate(
            method="sample_cov",
            as_of_date=pd.Timestamp(request.as_of_date),
            annualized=True,
            tickers=[],
            covariance_matrix=pd.DataFrame(),
            notes=["None of the requested tickers were available in return history."],
            invalid_tickers=invalid_tickers,
        )

    returns_wide = returns_wide[available_tickers].copy()
    returns_wide = returns_wide.dropna()

    if len(returns_wide) < config.min_history:
        notes.append(
            f"Insufficient aligned return history for covariance "
            f"({len(returns_wide)} < {config.min_history})."
        )
        return CovarianceEstimate(
            method="sample_cov",
            as_of_date=pd.Timestamp(request.as_of_date),
            annualized=True,
            tickers=available_tickers,
            covariance_matrix=pd.DataFrame(),
            notes=notes,
            invalid_tickers=invalid_tickers,
        )

    window_returns = returns_wide.tail(config.lookback_days)

    if len(window_returns) < config.min_history:
        notes.append(
            f"Insufficient lookback history after tail selection "
            f"({len(window_returns)} < {config.min_history})."
        )
        return CovarianceEstimate(
            method="sample_cov",
            as_of_date=pd.Timestamp(request.as_of_date),
            annualized=True,
            tickers=available_tickers,
            covariance_matrix=pd.DataFrame(),
            notes=notes,
            invalid_tickers=invalid_tickers,
        )

    covariance_matrix = window_returns.cov() * config.annualization_factor

    if covariance_matrix.empty:
        notes.append("Covariance matrix computed as empty.")
    else:
        covariance_matrix = covariance_matrix.loc[available_tickers, available_tickers]

    return CovarianceEstimate(
        method="sample_cov",
        as_of_date=pd.Timestamp(request.as_of_date),
        annualized=True,
        tickers=available_tickers,
        covariance_matrix=covariance_matrix,
        notes=notes,
        invalid_tickers=invalid_tickers,
    )


def _estimate_ewma_cov(
    request: CovarianceRequest,
    config: CovarianceConfig,
) -> CovarianceEstimate:
    df = request.etf_history.copy()

    required_columns = {"date", "ticker", "close"}
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(
            f"ETF history is missing required columns: {sorted(missing_columns)}"
        )

    if not 0.0 < config.ewma_lambda < 1.0:
        raise ValueError(
            f"ewma_lambda must be between 0 and 1 exclusive, got {config.ewma_lambda}."
        )

    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    as_of_date = pd.Timestamp(request.as_of_date).tz_localize(None)

    df = df[df["date"] < as_of_date].copy()

    if df.empty:
        return CovarianceEstimate(
            method="ewma_cov",
            as_of_date=pd.Timestamp(request.as_of_date),
            annualized=True,
            tickers=[],
            covariance_matrix=pd.DataFrame(),
            notes=["No ETF history available before as_of_date."],
            invalid_tickers=list(request.tickers),
        )

    df = df.sort_values(["ticker", "date"]).copy()
    df["return"] = df.groupby("ticker")["close"].pct_change()

    returns_wide = df.pivot(index="date", columns="ticker", values="return")

    requested_tickers = list(request.tickers)
    available_tickers = [
        ticker for ticker in requested_tickers
        if ticker in returns_wide.columns
    ]
    invalid_tickers = [
        ticker for ticker in requested_tickers
        if ticker not in returns_wide.columns
    ]

    notes: list[str] = []

    if not available_tickers:
        return CovarianceEstimate(
            method="ewma_cov",
            as_of_date=pd.Timestamp(request.as_of_date),
            annualized=True,
            tickers=[],
            covariance_matrix=pd.DataFrame(),
            notes=["None of the requested tickers were available in return history."],
            invalid_tickers=invalid_tickers,
        )

    returns_wide = returns_wide[available_tickers].copy()
    returns_wide = returns_wide.dropna()

    #lookback cap to reduce computation time
    returns_wide = returns_wide.tail(config.ewma_lookback_days)

    if len(returns_wide) < config.min_history:
        notes.append(
            f"Insufficient aligned return history for covariance "
            f"({len(returns_wide)} < {config.min_history})."
        )
        return CovarianceEstimate(
            method="ewma_cov",
            as_of_date=pd.Timestamp(request.as_of_date),
            annualized=True,
            tickers=available_tickers,
            covariance_matrix=pd.DataFrame(),
            notes=notes,
            invalid_tickers=invalid_tickers,
        )

    initial_window = returns_wide.iloc[:config.min_history]
    covariance_matrix = initial_window.cov()

    if covariance_matrix.empty:
        notes.append("Initial EWMA covariance matrix computed as empty.")
        return CovarianceEstimate(
            method="ewma_cov",
            as_of_date=pd.Timestamp(request.as_of_date),
            annualized=True,
            tickers=available_tickers,
            covariance_matrix=pd.DataFrame(),
            notes=notes,
            invalid_tickers=invalid_tickers,
        )

    covariance_matrix = covariance_matrix.loc[available_tickers, available_tickers]

    for _, row in returns_wide.iloc[config.min_history:].iterrows():
        r = row.to_numpy(dtype=float).reshape(-1, 1)
        outer = pd.DataFrame(
            r @ r.T,
            index=available_tickers,
            columns=available_tickers,
        )

        covariance_matrix = (
            config.ewma_lambda * covariance_matrix
            + (1.0 - config.ewma_lambda) * outer
        )

    covariance_matrix = covariance_matrix * config.annualization_factor

    if covariance_matrix.empty:
        notes.append("EWMA covariance matrix computed as empty.")
    else:
        covariance_matrix = covariance_matrix.loc[available_tickers, available_tickers]

    return CovarianceEstimate(
        method="ewma_cov",
        as_of_date=pd.Timestamp(request.as_of_date),
        annualized=True,
        tickers=available_tickers,
        covariance_matrix=covariance_matrix,
        notes=notes,
        invalid_tickers=invalid_tickers,
    )


def compute_portfolio_vol_from_covariance(
    weights: Dict[str, float],
    cov_estimate: CovarianceEstimate,
) -> float | None:
    if cov_estimate.covariance_matrix.empty:
        return None

    tickers = cov_estimate.tickers
    cov_matrix = cov_estimate.covariance_matrix

    # Build aligned weight vector
    w = np.array([float(weights.get(t, 0.0)) for t in tickers])

    # Convert covariance matrix to numpy
    sigma = cov_matrix.loc[tickers, tickers].values

    # Compute variance
    portfolio_var = float(w.T @ sigma @ w)

    if portfolio_var < 0:
        return None  # guard against numerical issues

    return float(np.sqrt(portfolio_var))