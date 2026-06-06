"""Date-alignment, long/wide reshaping, and lookahead safety of the returns view."""

import numpy as np
import pandas as pd
import pytest

from src.utils.ensure_long import ensure_long
from src.covariance.returns_view import CovarianceReturnsView

TICKERS = ["TLT", "AGG", "SHY"]


class TestEnsureLong:
    pytestmark = pytest.mark.unit

    def test_long_input_passes_through(self):
        df = pd.DataFrame(
            {"date": ["2020-01-01"], "ticker": ["TLT"], "close": [100.0]}
        )
        out = ensure_long(df)
        assert {"date", "ticker", "close"}.issubset(out.columns)

    def test_wide_input_is_melted_to_long(self):
        df = pd.DataFrame(
            {"date": ["2020-01-01", "2020-01-02"], "close_TLT": [100.0, 101.0], "close_AGG": [50.0, 51.0]}
        )
        out = ensure_long(df)
        assert {"date", "ticker", "close"}.issubset(out.columns)
        assert set(out["ticker"].unique()) == {"TLT", "AGG"}
        assert len(out) == 4

    def test_unrecognized_columns_raise(self):
        with pytest.raises(ValueError):
            ensure_long(pd.DataFrame({"date": ["2020-01-01"], "foo": [1.0]}))


@pytest.mark.lookahead
class TestReturnsViewWindow:
    def _view(self, etf_history):
        return CovarianceReturnsView.from_etf_history(
            etf_history=etf_history, tickers=TICKERS
        )

    def test_window_excludes_as_of_date(self, synthetic_etf_history):
        rv = self._view(synthetic_etf_history)
        as_of = rv.dates[100]
        window, available, _ = rv.get_window(
            as_of_date=as_of, tickers=TICKERS, lookback_days=1000
        )
        # Strictly before as_of (searchsorted side="left") -> no leakage.
        assert window.index.max() < as_of
        assert available == TICKERS

    def test_lookback_limits_window_length(self, synthetic_etf_history):
        rv = self._view(synthetic_etf_history)
        as_of = rv.dates[100]
        window, _, _ = rv.get_window(
            as_of_date=as_of, tickers=TICKERS, lookback_days=20
        )
        assert len(window) == 20

    def test_returns_are_aligned_across_tickers(self, synthetic_etf_history):
        rv = self._view(synthetic_etf_history)
        # Wide returns share one index; no per-ticker date drift, no NaNs after build.
        assert list(rv.returns_wide.columns) == TICKERS
        assert not rv.returns_wide.isna().any().any()
        assert rv.returns_wide.index.is_monotonic_increasing

    def test_invalid_ticker_reported(self, synthetic_etf_history):
        rv = self._view(synthetic_etf_history)
        _, available, invalid = rv.get_window(
            as_of_date=rv.dates[50], tickers=["TLT", "NOPE"], lookback_days=20
        )
        assert available == ["TLT"]
        assert invalid == ["NOPE"]


@pytest.mark.unit
class TestReturnsViewCache:
    def test_cache_hit_and_miss_accounting(self, synthetic_etf_history):
        rv = CovarianceReturnsView.from_etf_history(
            etf_history=synthetic_etf_history, tickers=TICKERS
        )
        key = ("k",)
        assert rv.get_cached_covariance(key) is None  # miss
        rv.set_cached_covariance(key, object())
        assert rv.get_cached_covariance(key) is not None  # hit
        assert rv.covariance_cache_hits == 1
        assert rv.covariance_cache_misses == 1
