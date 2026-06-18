"""Phase 1 — historical-percentile tests.

Cover the locked semantics of ``compute_rolling_percentile`` (point-in-time,
average ties, NaN handling, first-valid timing), the level classifier's
upper-edge boundary rule, a ``lookahead`` truncation guard, ticker independence,
and a benchmark that fails if the slow per-row ``apply`` path sneaks back in.
"""

import time

import numpy as np
import pandas as pd
import pytest

from src.volatility.percentiles import (
    LEVEL_INSUFFICIENT,
    VOL_LEVEL_THRESHOLDS,
    classify_volatility_level,
    compute_rolling_percentile,
    level_reference_lines,
    percentile_to_ordinal,
)


def _series(values):
    return pd.Series(values, dtype=float)


# --------------------------------------------------------------------------- #
# compute_rolling_percentile — locked semantics
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_constant_window_locked_value_is_average_not_one():
    # A length-4 all-tied window scores (k+1)/(2k) = 0.625 under method="average".
    out = compute_rolling_percentile(_series([5.0, 5.0, 5.0, 5.0]), window=4, min_periods=1)
    assert out.iloc[-1] == pytest.approx(0.625)
    # Long constant window tends to ~0.5 and must never be 1.0 (the rejected max-tie value).
    long_const = compute_rolling_percentile(_series([3.0] * 1000), window=1000, min_periods=1)
    assert long_const.iloc[-1] == pytest.approx(0.5, abs=0.01)
    assert long_const.iloc[-1] != pytest.approx(1.0)


@pytest.mark.unit
def test_rising_then_falling_last_value_rank():
    # Last value is the window max -> top of the range (1.0).
    rising = compute_rolling_percentile(_series([1, 2, 3, 4, 5]), window=5, min_periods=1)
    assert rising.iloc[-1] == pytest.approx(1.0)
    # Last value is the window min -> bottom (1/5).
    falling = compute_rolling_percentile(_series([5, 4, 3, 2, 1]), window=5, min_periods=1)
    assert falling.iloc[-1] == pytest.approx(0.2)


@pytest.mark.unit
def test_first_valid_only_after_min_periods():
    out = compute_rolling_percentile(_series(range(10)), window=10, min_periods=5)
    assert out.iloc[:4].isna().all()        # 1–4 observations: insufficient
    assert not pd.isna(out.iloc[4])         # 5th observation: first valid


@pytest.mark.unit
def test_missing_values_excluded_and_propagate_as_nan():
    out = compute_rolling_percentile(_series([1, 2, np.nan, 4, 5, np.nan, 7]), window=7, min_periods=1)
    # NaN inputs yield NaN percentiles, exactly at their positions.
    assert pd.isna(out.iloc[2]) and pd.isna(out.iloc[5])
    # The max of the non-NaN set {1,2,4,5,7} ranks at the top.
    assert out.iloc[6] == pytest.approx(1.0)
    # Earlier finite rows are unaffected by the later NaNs.
    assert not pd.isna(out.iloc[0])


@pytest.mark.unit
def test_expanding_full_window_uses_all_history():
    full = compute_rolling_percentile(_series([1, 2, 3, 4, 5]), window=None, min_periods=1)
    assert full.iloc[-1] == pytest.approx(1.0)   # 5 is the max of all 5
    assert full.iloc[0] == pytest.approx(1.0)    # first point is trivially the max of {1}


# --------------------------------------------------------------------------- #
# look-ahead guard + ticker independence
# --------------------------------------------------------------------------- #


@pytest.mark.lookahead
def test_truncation_does_not_change_past_percentiles():
    rng = np.random.default_rng(7)
    s = _series(rng.normal(size=400))
    full = compute_rolling_percentile(s, window=100, min_periods=50)
    cutoff = 300
    truncated = compute_rolling_percentile(s.iloc[: cutoff + 1], window=100, min_periods=50)
    pd.testing.assert_series_equal(
        full.iloc[: cutoff + 1], truncated, check_exact=False, rtol=1e-12
    )


@pytest.mark.unit
def test_tickers_are_ranked_independently():
    rng = np.random.default_rng(1)
    df = pd.DataFrame(
        {
            "ticker": ["TLT"] * 200 + ["SHY"] * 200,
            "vol": np.concatenate([rng.normal(0.12, 0.02, 200), rng.normal(0.012, 0.002, 200)]),
        }
    )
    per_group = df.groupby("ticker")["vol"].transform(
        lambda s: compute_rolling_percentile(s, window=100, min_periods=20)
    )
    # Re-computing one ticker in isolation must match the grouped result exactly,
    # i.e. SHY's tiny vols never leak into TLT's ranking.
    tlt_only = compute_rolling_percentile(
        df[df["ticker"] == "TLT"]["vol"].reset_index(drop=True), window=100, min_periods=20
    )
    pd.testing.assert_series_equal(
        per_group[df["ticker"] == "TLT"].reset_index(drop=True),
        tlt_only,
        check_names=False,
    )


# --------------------------------------------------------------------------- #
# classify_volatility_level — boundary determinism
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize(
    "percentile, expected",
    [
        (0.0, "Low"),
        (0.1999, "Low"),
        (0.20, "Normal"),     # upper-edge rule: exactly-on-threshold -> upper band
        (0.59, "Normal"),
        (0.60, "Elevated"),
        (0.79, "Elevated"),
        (0.80, "High"),
        (0.94, "High"),
        (0.95, "Extreme"),
        (1.0, "Extreme"),
    ],
)
def test_level_boundaries(percentile, expected):
    assert classify_volatility_level(percentile, VOL_LEVEL_THRESHOLDS) == expected


@pytest.mark.unit
def test_level_insufficient_history():
    assert classify_volatility_level(None) == LEVEL_INSUFFICIENT
    assert classify_volatility_level(float("nan")) == LEVEL_INSUFFICIENT


@pytest.mark.unit
def test_ordinal_and_reference_lines():
    assert percentile_to_ordinal(0.24) == 24
    assert percentile_to_ordinal(0.0) == 0
    assert percentile_to_ordinal(1.0) == 100
    assert percentile_to_ordinal(None) is None
    assert percentile_to_ordinal(float("nan")) is None
    assert level_reference_lines() == [0.20, 0.60, 0.80, 0.95]


# --------------------------------------------------------------------------- #
# performance: the vectorised path must stay fast (guards against a Python apply)
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_percentile_is_vectorised_and_fast():
    rng = np.random.default_rng(0)
    s = _series(rng.normal(size=2520))   # ~10Y of daily history
    start = time.perf_counter()
    out = compute_rolling_percentile(s, window=1260, min_periods=126)
    elapsed = time.perf_counter() - start
    assert out.notna().sum() > 2000
    # Vectorised rank is single-digit ms here; a per-row apply would take seconds.
    assert elapsed < 1.0
