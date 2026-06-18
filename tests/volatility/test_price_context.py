"""Phase 5 — price/volatility-context tests (as-of t-1, no look-ahead)."""

import numpy as np
import pandas as pd
import pytest

from src.volatility.price_context import (
    PRICE_DIRECTION_THRESHOLD,
    classify_price_volatility_context,
    compute_price_direction_features,
)

PT = PRICE_DIRECTION_THRESHOLD   # 0.01
VT = 0.10                         # vol-change threshold (matches Phase 2 rising/falling)


def _prices(values):
    return pd.Series(values, dtype=float)


# --------------------------------------------------------------------------- #
# as-of t-1 returns
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_price_returns_are_as_of_t_minus_1():
    # prices index:  0    1    2    3    4    5    6
    prices = _prices([100, 101, 102, 103, 104, 105, 106])
    feats = compute_price_direction_features(prices, horizons=(5,))
    # At t=6 the 5-day return ends at t-1=5: prices[5]/prices[0] - 1 = 105/100 - 1.
    assert feats["price_return_5d"].iloc[6] == pytest.approx(105 / 100 - 1)
    # The earliest rows lack a full lagged window -> NaN.
    assert feats["price_return_5d"].iloc[:5].isna().all()


@pytest.mark.lookahead
def test_changing_price_on_t_does_not_alter_row_t():
    prices = _prices(np.linspace(100, 130, 60))
    base = compute_price_direction_features(prices, horizons=(20,))
    t = 50
    bumped = prices.copy()
    bumped.iloc[t] = bumped.iloc[t] * 1.5   # spike the close *on* t
    after = compute_price_direction_features(bumped, horizons=(20,))
    # Row t (and earlier) use prices through t-1, so they are unchanged...
    pd.testing.assert_series_equal(
        base["price_return_20d"].iloc[: t + 1], after["price_return_20d"].iloc[: t + 1]
    )
    # ...while row t+1 (which reads price[t]) does change.
    assert base["price_return_20d"].iloc[t + 1] != pytest.approx(after["price_return_20d"].iloc[t + 1])


@pytest.mark.unit
def test_zero_prior_price_is_nan_not_inf():
    feats = compute_price_direction_features(_prices([0.0, 1.0, 2.0, 3.0]), horizons=(2,))
    # At t=3: lagged window is prices[2]/prices[0] = 2/0 -> inf -> NaN.
    assert pd.isna(feats["price_return_2d"].iloc[3])


# --------------------------------------------------------------------------- #
# joint classification
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize(
    "asset_return, vol_change, expected",
    [
        (-0.05, 0.20, "Adverse Shock"),                 # falling price, rising vol
        (0.05, 0.20, "Positive Volatility Expansion"),  # rising price, rising vol
        (0.05, -0.20, "Stable Positive Trend"),         # rising price, falling vol
        (-0.05, -0.20, "Controlled Decline"),           # falling price, falling vol
        (0.0, 0.0, "Quiet / Range-Bound"),              # flat price, stable vol
        (0.05, 0.0, "Quiet / Range-Bound"),             # partial: rising price, stable vol
        (0.0, 0.20, "Quiet / Range-Bound"),             # partial: flat price, rising vol
        (None, 0.20, "Unknown"),                        # missing price
        (0.05, None, "Unknown"),                        # missing vol
        (float("nan"), 0.2, "Unknown"),
    ],
)
def test_joint_classification(asset_return, vol_change, expected):
    assert classify_price_volatility_context(asset_return, vol_change, PT, VT) == expected


@pytest.mark.unit
def test_threshold_boundaries_count_as_flat_and_stable():
    # Exactly on the thresholds -> not directional (Flat / Stable) -> Quiet.
    assert classify_price_volatility_context(PT, VT, PT, VT) == "Quiet / Range-Bound"
    # Just beyond both -> a directional combo.
    assert classify_price_volatility_context(PT + 1e-9, VT + 1e-9, PT, VT) == "Positive Volatility Expansion"
