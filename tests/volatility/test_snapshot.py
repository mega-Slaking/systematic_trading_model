"""Phase 10 — passive strategy-integration snapshot tests.

Covers the contract: snapshot values match the underlying feature rows; historical
as-of queries return historical (not latest) values; future rows never affect an
earlier snapshot (look-ahead); missing optional features degrade safely; the
reproducibility metadata + both information-time dates are populated; and the
cross-asset snapshot carries per-asset snapshots + ratios + ranking.
"""

import numpy as np
import pandas as pd
import pytest

from src.volatility.models import VolatilityFeatureConfig, VolatilityFeatureSurface
from src.volatility.snapshot import (
    AssetVolatilitySignalSnapshot,
    VolatilitySignalSnapshotProvider,
)

_ESTIMATORS = ["rolling_20", "rolling_60", "ewma_94", "ewma_97", "garch"]


def _surface(n: int = 80, tickers=("TLT", "AGG"), config_key: str = "cfgA") -> VolatilityFeatureSurface:
    """A synthetic already-lagged surface: deterministic but varied vol per ticker."""
    dates = pd.bdate_range("2021-01-04", periods=n)
    frames = []
    for k, ticker in enumerate(tickers):
        rng = np.linspace(0.08 + 0.01 * k, 0.22 + 0.01 * k, n)
        wobble = 0.01 * np.sin(np.arange(n) / 3.0)
        base = rng + wobble
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "ticker": ticker,
                    "rolling_20": base,
                    "rolling_60": base * 0.9,
                    "ewma_94": base * 1.02,
                    "ewma_97": base * 0.98,
                    "garch": base * 1.05,
                    "config_key": config_key,
                }
            )
        )
    values = pd.concat(frames, ignore_index=True)
    return VolatilityFeatureSurface(values=values, config=VolatilityFeatureConfig(), tickers=list(tickers))


def _provider(surface=None, prices=None, **kw) -> VolatilitySignalSnapshotProvider:
    # Small minimum_history so percentiles form within the synthetic window.
    return VolatilitySignalSnapshotProvider(
        surface=surface or _surface(), prices=prices,
        historical_window="Full", minimum_history=5, stability_window="Full", **kw,
    )


def _prices(n: int = 80, tickers=("TLT", "AGG")) -> pd.DataFrame:
    dates = pd.bdate_range("2021-01-04", periods=n)
    frames = []
    for k, ticker in enumerate(tickers):
        close = 100.0 * (1.0 + 0.001 * (k + 1)) ** np.arange(n)
        frames.append(pd.DataFrame({"date": dates, "ticker": ticker, "close": close}))
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------------- #
# values match underlying rows + metadata
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_snapshot_values_match_underlying_row():
    surface = _surface()
    as_of = surface.values["date"].iloc[60]
    snap = _provider(surface).get_volatility_signal_snapshot("TLT", as_of)

    row = surface.get_ticker_snapshot(as_of, "TLT")
    assert snap.ticker == "TLT"
    assert snap.annualized_volatility == pytest.approx(float(row["rolling_20"]))
    assert snap.config_key == "cfgA"
    # Enough history -> percentile / level / state are populated (not Unknown/None).
    assert snap.historical_percentile is not None
    assert snap.volatility_level not in ("Insufficient history",)
    assert snap.confirmed_state != "Unknown" or snap.instantaneous_state != "Unknown"


@pytest.mark.unit
def test_snapshot_metadata_and_two_distinct_dates():
    surface = _surface()
    as_of = surface.values["date"].iloc[60]
    snap = _provider(surface).get_volatility_signal_snapshot("TLT", as_of)

    # Reproducibility metadata is populated.
    assert snap.reference_estimator == "rolling_20"
    assert snap.historical_window == "Full"
    assert snap.minimum_history == 5
    assert snap.state_config_version and snap.agreement_config_version
    assert snap.confirmation_days > 0
    assert snap.stability_window == "Full"
    # The lagged surface => as_of (t) and information_through (t-1) are distinct.
    tlt_dates = surface.values[surface.values["ticker"] == "TLT"]["date"].reset_index(drop=True)
    assert snap.as_of_date == pd.Timestamp(as_of)
    assert snap.information_through_date == tlt_dates.iloc[59]
    assert snap.information_through_date != snap.as_of_date


@pytest.mark.unit
def test_first_row_has_no_information_through_date():
    surface = _surface()
    first = surface.values[surface.values["ticker"] == "TLT"]["date"].iloc[0]
    snap = _provider(surface).get_volatility_signal_snapshot("TLT", first)
    assert snap.information_through_date is None


# --------------------------------------------------------------------------- #
# historical as-of retrieval + look-ahead safety
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_historical_as_of_returns_historical_values():
    surface = _surface()
    dates = surface.values[surface.values["ticker"] == "TLT"]["date"].reset_index(drop=True)
    early = _provider(surface).get_volatility_signal_snapshot("TLT", dates.iloc[40])
    late = _provider(surface).get_volatility_signal_snapshot("TLT", dates.iloc[70])
    # Different as-of dates read different underlying vol rows.
    assert early.as_of_date == dates.iloc[40]
    assert late.as_of_date == dates.iloc[70]
    assert early.annualized_volatility != late.annualized_volatility


@pytest.mark.lookahead
def test_future_rows_do_not_affect_earlier_snapshot():
    surface = _surface()
    dates = surface.values["date"].unique()
    as_of = pd.Timestamp(sorted(dates)[40])

    base = _provider(surface).get_volatility_signal_snapshot("TLT", as_of)

    # Mutate every row strictly after as_of, then re-snapshot the same date.
    mutated = surface.values.copy()
    future = mutated["date"] > as_of
    for col in _ESTIMATORS:
        mutated.loc[future, col] *= 3.0
    mutated_surface = VolatilityFeatureSurface(
        values=mutated, config=surface.config, tickers=surface.tickers
    )
    after = _provider(mutated_surface).get_volatility_signal_snapshot("TLT", as_of)

    assert after.annualized_volatility == pytest.approx(base.annualized_volatility)
    assert after.historical_percentile == pytest.approx(base.historical_percentile)
    assert after.confirmed_state == base.confirmed_state
    assert after.instantaneous_state == base.instantaneous_state


@pytest.mark.lookahead
def test_truncating_after_as_of_is_identical():
    surface = _surface()
    dates = sorted(surface.values["date"].unique())
    as_of = pd.Timestamp(dates[45])
    full = _provider(surface).get_volatility_signal_snapshot("AGG", as_of)

    truncated = surface.values[surface.values["date"] <= as_of].copy()
    trunc_surface = VolatilityFeatureSurface(values=truncated, config=surface.config, tickers=surface.tickers)
    trunc = _provider(trunc_surface).get_volatility_signal_snapshot("AGG", as_of)

    assert trunc.annualized_volatility == pytest.approx(full.annualized_volatility)
    assert trunc.historical_percentile == pytest.approx(full.historical_percentile)
    assert trunc.confirmed_state == full.confirmed_state


# --------------------------------------------------------------------------- #
# missing data degrades safely
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_missing_ticker_returns_blank_snapshot_with_metadata():
    surface = _surface()
    as_of = surface.values["date"].iloc[60]
    snap = _provider(surface).get_volatility_signal_snapshot("ZZZ", as_of)
    assert isinstance(snap, AssetVolatilitySignalSnapshot)
    assert snap.config_key == ""
    assert snap.confirmed_state == "Unknown"
    assert snap.annualized_volatility is None
    # Metadata still present so a consumer never sees a state without its context.
    assert snap.state_config_version and snap.as_of_date == pd.Timestamp(as_of)


@pytest.mark.unit
def test_price_fields_unknown_without_prices_and_present_with_prices():
    surface = _surface()
    as_of = surface.values["date"].iloc[70]

    no_prices = _provider(surface).get_volatility_signal_snapshot("TLT", as_of)
    assert no_prices.asset_return_20d is None
    assert no_prices.price_volatility_context == "Unknown"

    with_prices = _provider(surface, prices=_prices()).get_volatility_signal_snapshot("TLT", as_of)
    assert with_prices.asset_return_20d is not None
    assert with_prices.price_volatility_context != "Unknown"


# --------------------------------------------------------------------------- #
# cross-asset snapshot
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_cross_asset_snapshot_assets_ratios_ranking():
    surface = _surface()
    as_of = surface.values["date"].iloc[65]
    snap = _provider(surface, prices=_prices()).get_cross_asset_volatility_snapshot(as_of)

    assert {a.ticker for a in snap.assets} == {"TLT", "AGG"}
    assert snap.config_key == "cfgA"
    # Ranking covers every asset, ranks are 1..n and ordered by raw vol desc.
    assert [r.rank for r in snap.ranking] == [1, 2]
    vols = [r.annualized_volatility for r in snap.ranking]
    assert vols[0] >= vols[1]
    # The TLT/AGG ratio is present with its own historical context.
    pairs = {r.pair for r in snap.ratios}
    assert any("TLT" in p and "AGG" in p for p in pairs)


@pytest.mark.lookahead
def test_cross_asset_snapshot_is_point_in_time():
    surface = _surface()
    dates = sorted(surface.values["date"].unique())
    as_of = pd.Timestamp(dates[50])
    base = _provider(surface).get_cross_asset_volatility_snapshot(as_of)

    mutated = surface.values.copy()
    mutated.loc[mutated["date"] > as_of, _ESTIMATORS] *= 2.5
    mutated_surface = VolatilityFeatureSurface(values=mutated, config=surface.config, tickers=surface.tickers)
    after = _provider(mutated_surface).get_cross_asset_volatility_snapshot(as_of)

    base_tlt = next(a for a in base.assets if a.ticker == "TLT")
    after_tlt = next(a for a in after.assets if a.ticker == "TLT")
    assert after_tlt.historical_percentile == pytest.approx(base_tlt.historical_percentile)
    assert [r.pair for r in after.ratios] == [r.pair for r in base.ratios]
