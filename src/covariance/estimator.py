import pandas as pd
import numpy as np
from typing import Dict

from src.covariance.models import (
    CovarianceConfig,
    CovarianceEstimate,
    CovarianceRequest,
)

try:
    import fast_covariance_cpp # type: ignore[import-not-found]
except ImportError:
    fast_covariance_cpp = None


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


def _prepare_returns_wide(
    request: CovarianceRequest,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    df = request.etf_history.copy()

    required_columns = {"date", "ticker", "close"}
    missing_columns = required_columns.difference(df.columns)

    if missing_columns:
        raise ValueError(
            f"ETF history is missing required columns: {sorted(missing_columns)}"
        )

    requested_tickers = list(request.tickers)

    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    as_of_date = pd.Timestamp(request.as_of_date).tz_localize(None)

    df = df[df["date"] < as_of_date].copy()

    if df.empty:
        return pd.DataFrame(), [], requested_tickers

    df = df.sort_values(["ticker", "date"]).copy()
    df["return"] = df.groupby("ticker")["close"].pct_change()

    returns_wide = df.pivot(index="date", columns="ticker", values="return")

    available_tickers = [
        ticker for ticker in requested_tickers
        if ticker in returns_wide.columns
    ]

    invalid_tickers = [
        ticker for ticker in requested_tickers
        if ticker not in returns_wide.columns
    ]

    if not available_tickers:
        return pd.DataFrame(), [], invalid_tickers

    returns_wide = returns_wide[available_tickers].copy()
    returns_wide = returns_wide.dropna()

    return returns_wide, available_tickers, invalid_tickers


def _empty_estimate(
    *,
    method: str,
    request: CovarianceRequest,
    tickers: list[str],
    notes: list[str],
    invalid_tickers: list[str],
) -> CovarianceEstimate:
    return CovarianceEstimate(
        method=method,
        as_of_date=pd.Timestamp(request.as_of_date),
        annualized=True,
        tickers=tickers,
        covariance_matrix=pd.DataFrame(),
        notes=notes,
        invalid_tickers=invalid_tickers,
    )


def _estimate_sample_cov(
    request: CovarianceRequest,
    config: CovarianceConfig,
) -> CovarianceEstimate:
    method = "sample_cov"
    notes: list[str] = []

    returns_wide, available_tickers, invalid_tickers = _prepare_returns_wide(request)

    if not available_tickers:
        return _empty_estimate(
            method=method,
            request=request,
            tickers=[],
            notes=["None of the requested tickers were available in return history."],
            invalid_tickers=invalid_tickers,
        )

    if len(returns_wide) < config.min_history:
        notes.append(
            f"Insufficient aligned return history for covariance "
            f"({len(returns_wide)} < {config.min_history})."
        )

        return _empty_estimate(
            method=method,
            request=request,
            tickers=available_tickers,
            notes=notes,
            invalid_tickers=invalid_tickers,
        )

    window_returns = returns_wide.tail(config.lookback_days)

    if len(window_returns) < config.min_history:
        notes.append(
            f"Insufficient lookback history after tail selection "
            f"({len(window_returns)} < {config.min_history})."
        )

        return _empty_estimate(
            method=method,
            request=request,
            tickers=available_tickers,
            notes=notes,
            invalid_tickers=invalid_tickers,
        )

    if fast_covariance_cpp is not None:
        returns_np = np.ascontiguousarray(
            window_returns.to_numpy(dtype=np.float64)
        )

        covariance_np = fast_covariance_cpp.sample_covariance(
            returns_np,
            float(config.annualization_factor),
        )

        covariance_matrix = pd.DataFrame(
            np.asarray(covariance_np),
            index=available_tickers,
            columns=available_tickers,
        )
    else:
        notes.append("fast_covariance_cpp unavailable; used pandas fallback.")
        covariance_matrix = window_returns.cov() * config.annualization_factor
        covariance_matrix = covariance_matrix.loc[
            available_tickers,
            available_tickers,
        ]

    return CovarianceEstimate(
        method=method,
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
    method = "ewma_cov"
    notes: list[str] = []

    if not 0.0 < config.ewma_lambda < 1.0:
        raise ValueError(
            f"ewma_lambda must be between 0 and 1 exclusive, got {config.ewma_lambda}."
        )

    returns_wide, available_tickers, invalid_tickers = _prepare_returns_wide(request)

    if not available_tickers:
        return _empty_estimate(
            method=method,
            request=request,
            tickers=[],
            notes=["None of the requested tickers were available in return history."],
            invalid_tickers=invalid_tickers,
        )

    window_returns = returns_wide.tail(config.ewma_lookback_days)

    if len(window_returns) < config.min_history:
        notes.append(
            f"Insufficient aligned return history for covariance "
            f"({len(window_returns)} < {config.min_history})."
        )

        return _empty_estimate(
            method=method,
            request=request,
            tickers=available_tickers,
            notes=notes,
            invalid_tickers=invalid_tickers,
        )

    if fast_covariance_cpp is not None:
        returns_np = np.ascontiguousarray(
            window_returns.to_numpy(dtype=np.float64)
        )

        covariance_np = fast_covariance_cpp.ewma_covariance(
            returns_np,
            int(config.min_history),
            float(config.ewma_lambda),
            float(config.annualization_factor),
        )

        covariance_matrix = pd.DataFrame(
            np.asarray(covariance_np),
            index=available_tickers,
            columns=available_tickers,
        )
    else:
        notes.append("fast_covariance_cpp unavailable; used pandas fallback.")
        covariance_matrix = _estimate_ewma_cov_python_fallback(
            window_returns=window_returns,
            available_tickers=available_tickers,
            config=config,
        )

    return CovarianceEstimate(
        method=method,
        as_of_date=pd.Timestamp(request.as_of_date),
        annualized=True,
        tickers=available_tickers,
        covariance_matrix=covariance_matrix,
        notes=notes,
        invalid_tickers=invalid_tickers,
    )


def _estimate_ewma_cov_python_fallback(
    *,
    window_returns: pd.DataFrame,
    available_tickers: list[str],
    config: CovarianceConfig,
) -> pd.DataFrame:
    initial_window = window_returns.iloc[:config.min_history]
    covariance_matrix = initial_window.cov()

    covariance_matrix = covariance_matrix.loc[
        available_tickers,
        available_tickers,
    ]

    for _, row in window_returns.iloc[config.min_history:].iterrows():
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

    return covariance_matrix.loc[
        available_tickers,
        available_tickers,
    ]


def compute_portfolio_vol_from_covariance(
    weights: Dict[str, float],
    cov_estimate: CovarianceEstimate,
) -> float | None:
    if cov_estimate.covariance_matrix.empty:
        return None

    tickers = cov_estimate.tickers
    cov_matrix = cov_estimate.covariance_matrix

    w = np.array([float(weights.get(t, 0.0)) for t in tickers])

    sigma = cov_matrix.loc[tickers, tickers].values

    portfolio_var = float(w.T @ sigma @ w)

    if portfolio_var < 0:
        return None

    return float(np.sqrt(portfolio_var))