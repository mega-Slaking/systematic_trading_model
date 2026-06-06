"""Volatility feature surface tests (ported from the legacy validation script).

Validates the surface against the point-in-time estimator on deterministic
synthetic prices: matching the `date < t` estimator is also the lookahead guard.
"""

import pandas as pd
import pytest

from src.volatility.feature_surface import build_volatility_feature_surface
from src.volatility.models import (
    VolatilityFeatureConfig,
    VolatilityConfig,
    VolatilityRequest,
)
from src.volatility.estimator import estimate_volatility

pytestmark = [pytest.mark.regression, pytest.mark.lookahead]

TICKERS = ["TLT", "AGG", "SHY"]


def _surface(etf_history, **cfg):
    config = VolatilityFeatureConfig(min_history=20, **cfg)
    return build_volatility_feature_surface(
        etf_history=etf_history, tickers=TICKERS, config=config, lag_features_days=1
    )


def _surface_col(snapshot, column):
    return {
        row["ticker"]: float(row[column])
        for _, row in snapshot.iterrows()
        if pd.notna(row[column])
    }


def test_surface_returns_expected_columns(synthetic_etf_history):
    surface = _surface(
        synthetic_etf_history,
        rolling_windows=(20, 60),
        ewma_lambdas=(0.94, 0.97),
        include_garch=False,
    )
    feature_cols = set(surface.values.columns) - {"date", "ticker"}
    assert feature_cols == {
        "rolling_20",
        "rolling_60",
        "ewma_94",
        "ewma_97",
        "ewma_94_to_rolling_20",
        "ewma_94_change_5d",
        "ewma_97_to_rolling_20",
        "ewma_97_change_5d",
    }


def test_rolling_matches_point_estimator(synthetic_etf_history):
    surface = _surface(synthetic_etf_history, rolling_windows=(20,), ewma_lambdas=())
    as_of = pd.Timestamp(surface.values["date"].max())
    snap = surface.get_snapshot(as_of)

    point = estimate_volatility(
        request=VolatilityRequest(
            etf_history=synthetic_etf_history, as_of_date=as_of, tickers=TICKERS
        ),
        config=VolatilityConfig(method="rolling_std", lookback_days=20, min_history=20),
    )
    assert _surface_col(snap, "rolling_20") == pytest.approx(point.vols, abs=1e-9)


def test_ewma_matches_point_estimator(synthetic_etf_history):
    surface = _surface(synthetic_etf_history, rolling_windows=(), ewma_lambdas=(0.94,))
    as_of = pd.Timestamp(surface.values["date"].max())
    snap = surface.get_snapshot(as_of)

    point = estimate_volatility(
        request=VolatilityRequest(
            etf_history=synthetic_etf_history, as_of_date=as_of, tickers=TICKERS
        ),
        config=VolatilityConfig(method="ewma", ewma_lambda=0.94, min_history=20),
    )
    assert _surface_col(snap, "ewma_94") == pytest.approx(point.vols, abs=1e-9)


def test_comparison_feature_is_self_consistent(synthetic_etf_history):
    surface = _surface(
        synthetic_etf_history, rolling_windows=(20,), ewma_lambdas=(0.94,)
    )
    snap = surface.get_snapshot(pd.Timestamp(surface.values["date"].max()))
    for _, row in snap.iterrows():
        if pd.notna(row["ewma_94_to_rolling_20"]) and pd.notna(row["rolling_20"]):
            assert row["ewma_94_to_rolling_20"] == pytest.approx(
                row["ewma_94"] / row["rolling_20"]
            )


def test_snapshot_is_date_safe(synthetic_etf_history):
    surface = _surface(synthetic_etf_history, rolling_windows=(20,), ewma_lambdas=())
    as_of = pd.Timestamp(surface.values["date"].max())

    snap = surface.get_snapshot(as_of)
    assert not snap.empty
    assert (snap["date"] == as_of).all()

    # A date not in the panel yields an empty frame, never a guess.
    missing = surface.get_snapshot(pd.Timestamp("1990-01-01"))
    assert missing.empty


@pytest.mark.slow
def test_garch_daily_refit_matches_point_estimator(synthetic_etf_history):
    # Trim to keep daily-refit GARCH fast; daily refit must equal the estimator.
    df = synthetic_etf_history.copy()
    keep = sorted(df["date"].unique())[-90:]
    df = df[df["date"].isin(keep)]

    surface = build_volatility_feature_surface(
        etf_history=df,
        tickers=TICKERS,
        config=VolatilityFeatureConfig(
            rolling_windows=(),
            ewma_lambdas=(),
            include_garch=True,
            garch_refit_frequency="daily",
            garch_lookback_days=60,
            min_history=20,
        ),
        use_cache=False,
        lag_features_days=1,
    )
    as_of = pd.Timestamp(surface.values["date"].max())
    snap = surface.get_snapshot(as_of)

    point = estimate_volatility(
        request=VolatilityRequest(etf_history=df, as_of_date=as_of, tickers=TICKERS),
        config=VolatilityConfig(method="garch", garch_lookback_days=60, min_history=20),
    )
    assert _surface_col(snap, "garch") == pytest.approx(point.vols, abs=1e-6)
