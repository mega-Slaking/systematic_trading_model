"""Covariance estimation tests: shape/symmetry, portfolio-vol quadratic form,
and the C++ path agreeing with the pandas reference.
"""

import numpy as np
import pandas as pd
import pytest

from src.covariance.returns_view import CovarianceReturnsView
from src.covariance.estimator import (
    estimate_covariance_from_returns_view,
    compute_portfolio_vol_from_covariance,
)
from src.covariance.models import CovarianceConfig, CovarianceEstimate

pytestmark = pytest.mark.unit

TICKERS = ["TLT", "AGG", "SHY"]


def _view_and_asof(etf_history):
    rv = CovarianceReturnsView.from_etf_history(etf_history=etf_history, tickers=TICKERS)
    as_of = pd.Timestamp(etf_history["date"].max()) + pd.Timedelta(days=1)
    return rv, as_of


def _sample_estimate(rv, as_of):
    return estimate_covariance_from_returns_view(
        returns_view=rv,
        as_of_date=as_of,
        tickers=TICKERS,
        config=CovarianceConfig(
            method="sample_cov", lookback_days=60, annualization_factor=252, min_history=20
        ),
    )


def test_sample_cov_is_square_symmetric_positive_diagonal(synthetic_etf_history):
    rv, as_of = _view_and_asof(synthetic_etf_history)
    cov = _sample_estimate(rv, as_of).covariance_matrix

    assert list(cov.index) == TICKERS and list(cov.columns) == TICKERS
    assert np.allclose(cov.values, cov.values.T)
    assert (np.diag(cov.values) > 0).all()


def test_portfolio_vol_matches_quadratic_form(synthetic_etf_history):
    rv, as_of = _view_and_asof(synthetic_etf_history)
    est = _sample_estimate(rv, as_of)

    weights = {"TLT": 0.5, "AGG": 0.3, "SHY": 0.2}
    w = np.array([weights[t] for t in TICKERS])
    sigma = est.covariance_matrix.loc[TICKERS, TICKERS].values

    assert compute_portfolio_vol_from_covariance(weights, est) == pytest.approx(
        float(np.sqrt(w @ sigma @ w))
    )


def test_portfolio_vol_none_for_empty_covariance():
    empty = CovarianceEstimate(
        method="sample_cov",
        as_of_date=pd.Timestamp("2020-01-01"),
        annualized=True,
        tickers=[],
        covariance_matrix=pd.DataFrame(),
        notes=[],
        invalid_tickers=[],
    )
    assert compute_portfolio_vol_from_covariance({"TLT": 1.0}, empty) is None


def test_active_path_matches_pandas_reference(synthetic_etf_history):
    """The selected backend (C++ if present, else pandas) must equal pandas cov*ann."""
    rv, as_of = _view_and_asof(synthetic_etf_history)
    window, available, _ = rv.get_window(
        as_of_date=as_of, tickers=TICKERS, lookback_days=60
    )
    reference = (window.cov() * 252).loc[available, available].values

    est = _sample_estimate(rv, as_of)
    assert np.allclose(est.covariance_matrix.loc[available, available].values, reference, atol=1e-9)


def test_ewma_cov_is_symmetric_positive_diagonal(synthetic_etf_history):
    rv, as_of = _view_and_asof(synthetic_etf_history)
    est = estimate_covariance_from_returns_view(
        returns_view=rv,
        as_of_date=as_of,
        tickers=TICKERS,
        config=CovarianceConfig(
            method="ewma_cov", ewma_lambda=0.94, ewma_lookback_days=120, min_history=20
        ),
    )
    cov = est.covariance_matrix
    assert list(cov.index) == TICKERS
    assert np.allclose(cov.values, cov.values.T)
    assert (np.diag(cov.values) > 0).all()
