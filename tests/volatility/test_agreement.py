"""Phase 4 — estimator-agreement tests (relative dispersion + absolute-spread floor)."""

import numpy as np
import pandas as pd
import pytest

from src.volatility.agreement import (
    EstimatorAgreementConfig,
    classify_estimator_agreement,
    compute_estimator_dispersion,
)

ESTIMATORS = ["rolling_20", "rolling_60", "ewma_94", "ewma_97", "garch"]
CFG = EstimatorAgreementConfig()


def _row(rolling_20, rolling_60, ewma_94, ewma_97, garch):
    return pd.DataFrame(
        [{"rolling_20": rolling_20, "rolling_60": rolling_60, "ewma_94": ewma_94,
          "ewma_97": ewma_97, "garch": garch}]
    )


# --------------------------------------------------------------------------- #
# dispersion maths
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_dispersion_maths_and_highest_lowest():
    df = _row(0.10, 0.12, 0.11, 0.115, 0.13)
    out = compute_estimator_dispersion(df, ESTIMATORS, min_estimators=3)
    r = out.iloc[0]
    assert r["absolute_spread"] == pytest.approx(0.03)
    assert r["estimator_median"] == pytest.approx(0.115)
    assert r["relative_dispersion"] == pytest.approx(0.03 / 0.115)
    assert r["highest_estimator"] == "garch"
    assert r["lowest_estimator"] == "rolling_20"
    # fast premium = rolling_20 / median(rolling_60, ewma_97, garch) = 0.10 / 0.12.
    assert r["fast_premium"] == pytest.approx(0.10 / 0.12)


@pytest.mark.unit
def test_min_estimators_gate_nulls_dispersion():
    # Only two valid estimates, min_estimators=3 -> dispersion nulled.
    df = _row(0.10, 0.12, np.nan, np.nan, np.nan)
    out = compute_estimator_dispersion(df, ESTIMATORS, min_estimators=3)
    r = out.iloc[0]
    assert pd.isna(r["absolute_spread"])
    assert pd.isna(r["relative_dispersion"])
    assert pd.isna(r["highest_estimator"])


@pytest.mark.unit
def test_all_nan_row_does_not_raise():
    df = _row(np.nan, np.nan, np.nan, np.nan, np.nan)
    out = compute_estimator_dispersion(df, ESTIMATORS, min_estimators=3)
    assert pd.isna(out.iloc[0]["highest_estimator"])


@pytest.mark.unit
def test_missing_estimator_columns_are_tolerated():
    df = pd.DataFrame([{"rolling_20": 0.10, "rolling_60": 0.12, "ewma_94": 0.11}])
    out = compute_estimator_dispersion(df, ESTIMATORS, min_estimators=3)
    r = out.iloc[0]
    assert r["absolute_spread"] == pytest.approx(0.02)
    # slow set reduces to rolling_60 only -> fast premium = 0.10 / 0.12.
    assert r["fast_premium"] == pytest.approx(0.10 / 0.12)


@pytest.mark.unit
def test_no_row_multiplication():
    df = pd.concat([_row(0.10, 0.12, 0.11, 0.115, 0.13)] * 7, ignore_index=True)
    out = compute_estimator_dispersion(df, ESTIMATORS, min_estimators=3)
    assert len(out) == len(df)


# --------------------------------------------------------------------------- #
# classification: the both-gates rule + the SHY floor
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize(
    "relative, absolute, expected",
    [
        (0.05, 0.02, "High"),       # below high threshold
        (0.0999, 0.02, "High"),
        (0.10, 0.02, "Moderate"),   # exactly on high edge -> not High
        (0.15, 0.02, "Moderate"),
        (0.25, 0.02, "Moderate"),   # exactly on low edge -> not Low
        (0.30, 0.02, "Low"),        # both gates breached
        (None, 0.02, "Unknown"),
        (0.30, None, "Unknown"),
    ],
)
def test_agreement_boundaries(relative, absolute, expected):
    assert classify_estimator_agreement(relative, absolute, CFG) == expected


@pytest.mark.unit
def test_absolute_floor_prevents_false_low_for_shy():
    # SHY-like: 25%+ relative dispersion but a trivial absolute spread (< floor).
    # Relative alone would say "Low"; the absolute floor keeps it "Moderate".
    assert classify_estimator_agreement(0.30, 0.0012, CFG) == "Moderate"
    # The same relative with a real absolute spread is genuinely Low.
    assert classify_estimator_agreement(0.30, 0.01, CFG) == "Low"


@pytest.mark.unit
def test_zero_median_is_unknown_not_crash():
    df = _row(0.0, 0.0, 0.0, 0.0, 0.0)
    out = compute_estimator_dispersion(df, ESTIMATORS, min_estimators=3)
    rd = out.iloc[0]["relative_dispersion"]
    assert pd.isna(rd)
    assert classify_estimator_agreement(rd, 0.0, CFG) == "Unknown"


@pytest.mark.unit
def test_config_version_changes_with_floor():
    base = EstimatorAgreementConfig().version()
    assert EstimatorAgreementConfig().version() == base
    assert EstimatorAgreementConfig(low_agreement_absolute_floor=0.005).version() != base
