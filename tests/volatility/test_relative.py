"""Phase 7 — cross-asset relative-volatility tests."""

import numpy as np
import pandas as pd
import pytest

from src.volatility.relative import (
    build_cross_asset_risk_table,
    compute_relative_volatility_ratios,
    default_ratio_pairs,
)


def _wide(tlt, agg, shy):
    idx = pd.bdate_range("2021-01-01", periods=len(tlt))
    return pd.DataFrame({"TLT": tlt, "AGG": agg, "SHY": shy}, index=idx)


# --------------------------------------------------------------------------- #
# ratios
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_default_pairs_are_duration_ordered():
    assert default_ratio_pairs(["SHY", "TLT", "AGG"]) == [("TLT", "AGG"), ("TLT", "SHY"), ("AGG", "SHY")]


@pytest.mark.unit
def test_ratio_maths():
    wide = _wide([0.12, 0.10], [0.06, 0.05], [0.02, 0.02])
    ratios = compute_relative_volatility_ratios(wide, default_ratio_pairs(["TLT", "AGG", "SHY"]))
    assert list(ratios.columns) == ["TLT/AGG", "TLT/SHY", "AGG/SHY"]
    assert ratios["TLT/AGG"].tolist() == pytest.approx([2.0, 2.0])
    assert ratios["TLT/SHY"].iloc[0] == pytest.approx(6.0)
    assert ratios["AGG/SHY"].iloc[0] == pytest.approx(3.0)


@pytest.mark.unit
def test_ratio_division_by_zero_is_nan():
    wide = _wide([0.1, 0.1], [0.0, 0.05], [0.02, 0.02])
    ratios = compute_relative_volatility_ratios(wide, [("TLT", "AGG")])
    assert pd.isna(ratios["TLT/AGG"].iloc[0])     # 0.1 / 0.0 -> inf -> NaN
    assert ratios["TLT/AGG"].iloc[1] == pytest.approx(2.0)


@pytest.mark.unit
def test_missing_asset_pair_skipped():
    wide = pd.DataFrame({"TLT": [0.1], "AGG": [0.05]}, index=pd.bdate_range("2021-01-01", periods=1))
    ratios = compute_relative_volatility_ratios(wide, [("TLT", "AGG"), ("TLT", "SHY")])
    assert list(ratios.columns) == ["TLT/AGG"]    # the SHY pair is silently dropped


@pytest.mark.unit
def test_ratios_are_per_pair_independent():
    # Each column depends only on its own two assets; bumping SHY moves only *_SHY pairs.
    base = _wide([0.12] * 3, [0.06] * 3, [0.02] * 3)
    pairs = default_ratio_pairs(["TLT", "AGG", "SHY"])
    r0 = compute_relative_volatility_ratios(base, pairs)
    bumped = base.copy()
    bumped["SHY"] = 0.04
    r1 = compute_relative_volatility_ratios(bumped, pairs)
    pd.testing.assert_series_equal(r0["TLT/AGG"], r1["TLT/AGG"])           # unaffected
    assert not np.allclose(r0["TLT/SHY"], r1["TLT/SHY"])                   # changed


# --------------------------------------------------------------------------- #
# ranking
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_risk_ranking_by_current_vol_desc():
    rows = pd.DataFrame(
        {
            "ticker": ["SHY", "TLT", "AGG"],
            "current_volatility": [0.013, 0.090, 0.044],
            "percentile_ordinal": [18, 24, 35],
            "confirmed_state": ["Calm", "Calm", "Calm"],
        }
    )
    ranked = build_cross_asset_risk_table(rows)
    assert ranked["ticker"].tolist() == ["TLT", "AGG", "SHY"]   # highest vol first
    assert ranked["rank"].tolist() == [1, 2, 3]


@pytest.mark.unit
def test_risk_ranking_handles_missing_vol():
    rows = pd.DataFrame(
        {"ticker": ["TLT", "AGG"], "current_volatility": [np.nan, 0.04],
         "percentile_ordinal": [None, 30], "confirmed_state": ["Unknown", "Calm"]}
    )
    ranked = build_cross_asset_risk_table(rows)
    assert ranked.iloc[0]["ticker"] == "AGG"      # NaN vol sorts last
    assert ranked["rank"].tolist() == [1, 2]
