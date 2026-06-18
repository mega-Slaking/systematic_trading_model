"""Phase 2 — volatility direction + 20D/60D term-ratio tests."""

import numpy as np
import pandas as pd
import pytest

from src.volatility.direction import (
    VOL_DIRECTION_THRESHOLDS,
    VOL_RATIO_BANDS,
    change_reference_lines,
    classify_volatility_direction,
    classify_volatility_term_state,
    compute_volatility_direction_features,
    compute_volatility_term_ratio,
    ratio_reference_lines,
)

RISING = VOL_DIRECTION_THRESHOLDS["rising"]
FALLING = VOL_DIRECTION_THRESHOLDS["falling"]
EXPANSION = VOL_RATIO_BANDS["expansion"]
CONTRACTION = VOL_RATIO_BANDS["contraction"]


def _series(values):
    return pd.Series(values, dtype=float)


# --------------------------------------------------------------------------- #
# change + ratio maths
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_relative_change_maths():
    vol = _series([0.10, 0.11, 0.12, 0.13, 0.14, 0.15])
    feats = compute_volatility_direction_features(vol, short_change_days=5, long_change_days=20)
    assert list(feats.columns) == ["change_5d", "change_20d"]
    # 5-day relative change at index 5: 0.15 / 0.10 - 1 = 0.5.
    assert feats["change_5d"].iloc[5] == pytest.approx(0.5)
    # The first `short_change_days` rows have no prior reference -> NaN.
    assert feats["change_5d"].iloc[:5].isna().all()
    # 20-day change never has enough history here -> all NaN.
    assert feats["change_20d"].isna().all()


@pytest.mark.unit
def test_term_ratio_maths():
    ratio = compute_volatility_term_ratio(_series([0.12, 0.10]), _series([0.10, 0.10]))
    assert ratio.tolist() == pytest.approx([1.2, 1.0])


@pytest.mark.unit
def test_term_ratio_division_by_zero_is_nan():
    ratio = compute_volatility_term_ratio(_series([0.1, 0.1]), _series([0.0, 0.1]))
    assert pd.isna(ratio.iloc[0])      # 0.1 / 0.0 -> inf -> NaN, not inf
    assert ratio.iloc[1] == pytest.approx(1.0)


@pytest.mark.unit
def test_missing_long_vol_gives_nan_ratio_and_unknown_state():
    ratio = compute_volatility_term_ratio(_series([0.1, 0.1]), _series([np.nan, np.nan]))
    assert ratio.isna().all()
    assert classify_volatility_term_state(None, EXPANSION, CONTRACTION) == "Unknown"
    assert classify_volatility_term_state(float("nan"), EXPANSION, CONTRACTION) == "Unknown"


# --------------------------------------------------------------------------- #
# classifier boundary determinism
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize(
    "change, expected",
    [
        (0.10, "Rising"),     # exactly on the rising threshold -> Rising
        (0.0999, "Stable"),
        (0.0, "Stable"),
        (-0.0999, "Stable"),
        (-0.10, "Falling"),   # exactly on the falling threshold -> Falling
        (-0.5, "Falling"),
        (None, "Unknown"),
        (float("nan"), "Unknown"),
    ],
)
def test_direction_boundaries(change, expected):
    assert classify_volatility_direction(change, RISING, FALLING) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "ratio, expected",
    [
        (1.15, "Expansion"),     # exactly on the expansion band -> Expansion
        (1.1499, "Balanced"),
        (1.0, "Balanced"),
        (0.8501, "Balanced"),
        (0.85, "Contraction"),   # exactly on the contraction band -> Contraction
        (0.5, "Contraction"),
        (None, "Unknown"),
        (float("nan"), "Unknown"),
    ],
)
def test_term_state_boundaries(ratio, expected):
    assert classify_volatility_term_state(ratio, EXPANSION, CONTRACTION) == expected


@pytest.mark.unit
def test_reference_lines():
    assert ratio_reference_lines() == [0.85, 1.00, 1.15]
    assert change_reference_lines() == [-0.10, 0.00, 0.10]


# --------------------------------------------------------------------------- #
# point-in-time + independence
# --------------------------------------------------------------------------- #


@pytest.mark.lookahead
def test_changes_are_point_in_time_under_truncation():
    rng = np.random.default_rng(11)
    s = _series(np.abs(rng.normal(0.1, 0.02, 220)))
    full = compute_volatility_direction_features(s)
    cutoff = 150
    truncated = compute_volatility_direction_features(s.iloc[: cutoff + 1])
    pd.testing.assert_frame_equal(
        full.iloc[: cutoff + 1], truncated, check_exact=False, rtol=1e-12
    )


@pytest.mark.unit
def test_no_cross_asset_leakage():
    rng = np.random.default_rng(3)
    df = pd.DataFrame(
        {
            "ticker": ["TLT"] * 100 + ["SHY"] * 100,
            "vol": np.concatenate([rng.normal(0.12, 0.02, 100), rng.normal(0.012, 0.002, 100)]),
        }
    )
    grouped = df.groupby("ticker")["vol"].apply(
        lambda s: compute_volatility_direction_features(s.reset_index(drop=True))["change_20d"]
    )
    tlt_only = compute_volatility_direction_features(
        df[df["ticker"] == "TLT"]["vol"].reset_index(drop=True)
    )["change_20d"]
    np.testing.assert_allclose(
        grouped.loc["TLT"].to_numpy(), tlt_only.to_numpy(), equal_nan=True
    )
