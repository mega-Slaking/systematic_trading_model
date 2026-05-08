import pandas as pd
import numpy as np
from typing import Dict

from src.covariance.models import (
    CovarianceConfig,
    CovarianceEstimate,
)
from src.covariance.returns_view import CovarianceReturnsView

try:
    import fast_covariance_cpp # type: ignore[import-not-found]
except ImportError:
    fast_covariance_cpp = None


def estimate_covariance_from_returns_view(
    *,
    returns_view: CovarianceReturnsView,
    as_of_date,
    tickers: list[str],
    config: CovarianceConfig | None = None,
) -> CovarianceEstimate:
    config = config or CovarianceConfig()

    cache_key = _make_returns_view_cache_key(
        as_of_date=as_of_date,
        tickers=tickers,
        config=config,
    )

    cached_estimate = returns_view.get_cached_covariance(cache_key)

    if cached_estimate is not None:
        return cached_estimate

    if config.method == "sample_cov":
        estimate = _estimate_sample_cov_from_returns_view(
            returns_view=returns_view,
            as_of_date=as_of_date,
            tickers=tickers,
            config=config,
        )

    elif config.method == "ewma_cov":
        estimate = _estimate_ewma_cov_from_returns_view(
            returns_view=returns_view,
            as_of_date=as_of_date,
            tickers=tickers,
            config=config,
        )

    else:
        raise ValueError(f"Unsupported covariance method: {config.method}")

    returns_view.set_cached_covariance(cache_key, estimate)

    return estimate


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


def _empty_estimate_for_date(
    *,
    method: str,
    as_of_date,
    tickers: list[str],
    notes: list[str],
    invalid_tickers: list[str],
) -> CovarianceEstimate:
    return CovarianceEstimate(
        method=method,
        as_of_date=pd.Timestamp(as_of_date),
        annualized=True,
        tickers=tickers,
        covariance_matrix=pd.DataFrame(),
        notes=notes,
        invalid_tickers=invalid_tickers,
    )


def _estimate_sample_cov_from_returns_view(
    *,
    returns_view: CovarianceReturnsView,
    as_of_date,
    tickers: list[str],
    config: CovarianceConfig,
) -> CovarianceEstimate:
    method = "sample_cov"
    notes: list[str] = []

    window_returns, available_tickers, invalid_tickers = returns_view.get_window(
        as_of_date=as_of_date,
        tickers=tickers,
        lookback_days=config.lookback_days,
    )

    if not available_tickers:
        return _empty_estimate_for_date(
            method=method,
            as_of_date=as_of_date,
            tickers=[],
            notes=["None of the requested tickers were available in return history."],
            invalid_tickers=invalid_tickers,
        )

    if len(window_returns) < config.min_history:
        notes.append(
            f"Insufficient lookback history after tail selection "
            f"({len(window_returns)} < {config.min_history})."
        )

        return _empty_estimate_for_date(
            method=method,
            as_of_date=as_of_date,
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
        as_of_date=pd.Timestamp(as_of_date),
        annualized=True,
        tickers=available_tickers,
        covariance_matrix=covariance_matrix,
        notes=notes,
        invalid_tickers=invalid_tickers,
    )


def _estimate_ewma_cov_from_returns_view(
    *,
    returns_view: CovarianceReturnsView,
    as_of_date,
    tickers: list[str],
    config: CovarianceConfig,
) -> CovarianceEstimate:
    method = "ewma_cov"
    notes: list[str] = []

    if not 0.0 < config.ewma_lambda < 1.0:
        raise ValueError(
            f"ewma_lambda must be between 0 and 1 exclusive, got {config.ewma_lambda}."
        )

    window_returns, available_tickers, invalid_tickers = returns_view.get_window(
        as_of_date=as_of_date,
        tickers=tickers,
        lookback_days=config.ewma_lookback_days,
    )

    if not available_tickers:
        return _empty_estimate_for_date(
            method=method,
            as_of_date=as_of_date,
            tickers=[],
            notes=["None of the requested tickers were available in return history."],
            invalid_tickers=invalid_tickers,
        )

    if len(window_returns) < config.min_history:
        notes.append(
            f"Insufficient aligned return history for covariance "
            f"({len(window_returns)} < {config.min_history})."
        )

        return _empty_estimate_for_date(
            method=method,
            as_of_date=as_of_date,
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
        as_of_date=pd.Timestamp(as_of_date),
        annualized=True,
        tickers=available_tickers,
        covariance_matrix=covariance_matrix,
        notes=notes,
        invalid_tickers=invalid_tickers,
    )


def _make_returns_view_cache_key(
    *,
    as_of_date,
    tickers: list[str],
    config: CovarianceConfig,
) -> tuple:
    as_of_date = pd.Timestamp(as_of_date).tz_localize(None)

    return (
        as_of_date,
        tuple(tickers),
        config.method,
        config.lookback_days,
        config.ewma_lookback_days,
        config.min_history,
        config.annualization_factor,
        config.ewma_lambda,
    )