"""Phase 8 — volatility-of-volatility + estimate-stability tests."""

import numpy as np
import pandas as pd
import pytest

from src.volatility.percentiles import compute_rolling_percentile
from src.volatility.stability import (
    STABILITY_THRESHOLDS,
    classify_estimate_stability,
    compute_volatility_of_volatility,
    stability_reference_lines,
)


def _series(values):
    return pd.Series(values, dtype=float)


# --------------------------------------------------------------------------- #
# compute_volatility_of_volatility
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_vov_rolling_std_of_changes():
    # Linear ramp: daily change is constant, so its rolling std is 0.
    vov = compute_volatility_of_volatility(_series(np.arange(30, dtype=float)), window=5)
    assert vov.iloc[-1] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.unit
def test_vov_warmup_is_nan():
    vov = compute_volatility_of_volatility(_series(np.arange(30, dtype=float)), window=20)
    # diff drops 1, rolling(20) needs 20 -> first ~20 rows NaN.
    assert vov.iloc[:19].isna().all()
    assert not pd.isna(vov.iloc[-1])


@pytest.mark.unit
def test_constant_volatility_is_stable():
    # A perfectly flat vol estimate -> vov == 0 everywhere -> low percentile -> Stable.
    vov = compute_volatility_of_volatility(_series([0.12] * 200), window=20)
    pct = compute_rolling_percentile(vov, window=120, min_periods=20)
    assert classify_estimate_stability(pct.iloc[-1]) == "Stable"


@pytest.mark.unit
def test_missing_observations_propagate_nan():
    s = _series([0.1, 0.11, np.nan, 0.13, 0.14, 0.16, 0.2, 0.1])
    vov = compute_volatility_of_volatility(s, window=3)
    assert vov.isna().any()        # the NaN region yields NaN vov, no crash


# --------------------------------------------------------------------------- #
# classify_estimate_stability — boundary determinism
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize(
    "percentile, expected",
    [
        (0.0, "Stable"),
        (0.59, "Stable"),
        (0.60, "Changing"),
        (0.79, "Changing"),
        (0.80, "Unstable"),
        (0.95, "Unstable"),        # 0.80–0.95 inclusive
        (0.951, "Extreme instability"),  # strictly above 0.95
        (1.0, "Extreme instability"),
        (None, "Unknown"),
        (float("nan"), "Unknown"),
    ],
)
def test_stability_boundaries(percentile, expected):
    assert classify_estimate_stability(percentile, STABILITY_THRESHOLDS) == expected


@pytest.mark.unit
def test_reference_lines():
    assert stability_reference_lines() == [0.60, 0.80, 0.95]


# --------------------------------------------------------------------------- #
# point-in-time
# --------------------------------------------------------------------------- #


@pytest.mark.lookahead
def test_vov_and_percentile_are_point_in_time():
    rng = np.random.default_rng(5)
    s = _series(np.abs(rng.normal(0.1, 0.02, 300)))
    vov_full = compute_volatility_of_volatility(s, window=20)
    pct_full = compute_rolling_percentile(vov_full, window=120, min_periods=20)

    cutoff = 200
    vov_trunc = compute_volatility_of_volatility(s.iloc[: cutoff + 1], window=20)
    pct_trunc = compute_rolling_percentile(vov_trunc, window=120, min_periods=20)

    pd.testing.assert_series_equal(vov_full.iloc[: cutoff + 1], vov_trunc, check_exact=False, rtol=1e-12)
    pd.testing.assert_series_equal(pct_full.iloc[: cutoff + 1], pct_trunc, check_exact=False, rtol=1e-12)
