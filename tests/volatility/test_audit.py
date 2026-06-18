"""Phase 0 — volatility-surface data-contract tests.

Two layers:

* Pure-frame checks of ``validate_/normalize_volatility_surface`` and
  ``surface_data_version`` on small hand-built frames (``unit``).
* A ``lookahead`` guard that the single one-day lag is genuinely point-in-time:
  truncating every row after ``t`` must leave every value on/before ``t``
  unchanged. This is the contract that derived features are never re-shifted.
"""

import numpy as np
import pandas as pd
import pytest

from src.volatility.audit import (
    normalize_volatility_surface,
    surface_data_version,
    validate_volatility_surface,
)
from src.volatility.constants import VOL_ESTIMATOR_NAMES
from src.volatility.feature_surface import build_volatility_feature_surface
from src.volatility.models import VolatilityFeatureConfig

TICKERS = ["TLT", "AGG", "SHY"]
_PRESENT_ESTIMATORS = ["rolling_20", "rolling_60", "ewma_94", "ewma_97"]


def _build(etf_history, **cfg):
    """Surface over the four non-GARCH estimators (fast, deterministic)."""
    config = VolatilityFeatureConfig(
        rolling_windows=(20, 60),
        ewma_lambdas=(0.94, 0.97),
        include_garch=False,
        min_history=20,
        **cfg,
    )
    return build_volatility_feature_surface(
        etf_history=etf_history,
        tickers=TICKERS,
        config=config,
        lag_features_days=1,
        use_cache=False,
    )


def _toy_surface() -> pd.DataFrame:
    """A tiny, clean, single-config_key surface frame."""
    dates = pd.bdate_range("2021-01-01", periods=4)
    rows = []
    for ticker, base in (("TLT", 0.10), ("AGG", 0.05)):
        for i, d in enumerate(dates):
            rows.append(
                {
                    "date": d,
                    "ticker": ticker,
                    "rolling_20": base + i * 0.001,
                    "rolling_60": base + i * 0.001,
                    "ewma_94": base + i * 0.001,
                    "ewma_97": base + i * 0.001,
                    "garch": base + i * 0.001,
                    "config_key": "cfgA",
                }
            )
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# validate_volatility_surface
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_validate_clean_surface_returns_no_warnings(synthetic_etf_history):
    surface = _build(synthetic_etf_history)
    df = surface.values.assign(config_key="cfgA")
    assert validate_volatility_surface(df, _PRESENT_ESTIMATORS) == []


@pytest.mark.unit
def test_validate_missing_estimator_column(synthetic_etf_history):
    surface = _build(synthetic_etf_history)  # no garch column built
    warnings = validate_volatility_surface(surface.values, VOL_ESTIMATOR_NAMES)
    assert any("missing estimator column" in w and "garch" in w for w in warnings)


@pytest.mark.unit
def test_validate_duplicate_keys():
    df = _toy_surface()
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    warnings = validate_volatility_surface(dup, _PRESENT_ESTIMATORS)
    assert any("duplicate" in w for w in warnings)


@pytest.mark.unit
def test_validate_negative_volatility():
    df = _toy_surface()
    df.loc[0, "rolling_20"] = -0.01
    warnings = validate_volatility_surface(df, _PRESENT_ESTIMATORS)
    assert any("negative volatility" in w and "rolling_20" in w for w in warnings)


@pytest.mark.unit
def test_validate_non_monotonic_dates():
    df = _toy_surface()
    # Reverse TLT's rows so its dates are descending in row order.
    tlt = df[df["ticker"] == "TLT"].iloc[::-1]
    rest = df[df["ticker"] != "TLT"]
    warnings = validate_volatility_surface(
        pd.concat([tlt, rest], ignore_index=True), _PRESENT_ESTIMATORS
    )
    assert any("monotonic" in w and "TLT" in w for w in warnings)


@pytest.mark.unit
def test_validate_multiple_config_keys_warns():
    df = _toy_surface()
    df.loc[df["ticker"] == "AGG", "config_key"] = "cfgB"
    warnings = validate_volatility_surface(df, _PRESENT_ESTIMATORS)
    assert any("config_key" in w for w in warnings)


@pytest.mark.unit
def test_validate_percentage_scale_heuristic():
    df = _toy_surface()
    df.loc[0, "rolling_20"] = 8.97  # 897% as a decimal -> implausible
    warnings = validate_volatility_surface(df, _PRESENT_ESTIMATORS)
    assert any("decimals" in w for w in warnings)


@pytest.mark.unit
def test_validate_empty_surface():
    assert validate_volatility_surface(pd.DataFrame(), _PRESENT_ESTIMATORS) == ["surface is empty"]


# --------------------------------------------------------------------------- #
# normalize_volatility_surface
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_normalize_orders_columns_and_sorts():
    df = _toy_surface()
    # Shuffle rows and columns.
    scrambled = df.sample(frac=1.0, random_state=1)[
        ["config_key", "ewma_97", "ticker", "rolling_20", "date", "garch", "rolling_60", "ewma_94"]
    ]
    out = normalize_volatility_surface(scrambled)
    assert list(out.columns)[:2] == ["date", "ticker"]
    assert list(out.columns)[2:7] == VOL_ESTIMATOR_NAMES
    assert out.columns[-1] == "config_key"
    # Sorted by (ticker, date): AGG before TLT, ascending dates within ticker.
    assert out["ticker"].tolist() == ["AGG"] * 4 + ["TLT"] * 4
    assert out[out["ticker"] == "AGG"]["date"].is_monotonic_increasing


@pytest.mark.unit
def test_normalize_coerces_date_dtype():
    df = _toy_surface()
    df["date"] = df["date"].astype(str)  # strings in -> datetime out
    out = normalize_volatility_surface(df)
    assert pd.api.types.is_datetime64_any_dtype(out["date"])


@pytest.mark.unit
def test_normalize_preserves_warmup_nan_rows():
    df = _toy_surface()
    df.loc[df["ticker"] == "TLT", _PRESENT_ESTIMATORS + ["garch"]] = np.nan
    out = normalize_volatility_surface(df)
    assert len(out) == len(df)  # nothing dropped
    tlt = out[out["ticker"] == "TLT"]
    assert tlt["rolling_20"].isna().all()


@pytest.mark.unit
def test_normalize_raises_on_multiple_config_keys():
    df = _toy_surface()
    df.loc[df["ticker"] == "AGG", "config_key"] = "cfgB"
    with pytest.raises(ValueError, match="single config_key"):
        normalize_volatility_surface(df)


@pytest.mark.unit
def test_normalize_raises_on_missing_keys():
    df = _toy_surface().drop(columns=["ticker"])
    with pytest.raises(ValueError, match="key column"):
        normalize_volatility_surface(df)


# --------------------------------------------------------------------------- #
# surface_data_version
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_surface_data_version_changes_when_row_appended():
    df = _toy_surface()
    base = surface_data_version(df)
    grown = pd.concat(
        [df, df.iloc[[-1]].assign(date=pd.Timestamp("2021-01-08"))],
        ignore_index=True,
    )
    assert surface_data_version(grown) != base
    assert surface_data_version(pd.DataFrame()) == ("", 0)


# --------------------------------------------------------------------------- #
# one-day lag is genuinely point-in-time (the never-re-shift contract)
# --------------------------------------------------------------------------- #


@pytest.mark.lookahead
def test_one_day_lag_equivalence_under_truncation(synthetic_etf_history):
    """Truncating rows after t must not change any value on/before t."""
    all_dates = sorted(pd.to_datetime(synthetic_etf_history["date"]).unique())
    cutoff = all_dates[150]

    full = _build(synthetic_etf_history)
    truncated_history = synthetic_etf_history[
        pd.to_datetime(synthetic_etf_history["date"]) <= cutoff
    ]
    truncated = _build(truncated_history)

    feature_cols = [c for c in full.values.columns if c not in ("date", "ticker")]

    def _le_cutoff(values: pd.DataFrame) -> pd.DataFrame:
        sub = values[values["date"] <= cutoff]
        return sub.set_index(["ticker", "date"])[feature_cols].sort_index()

    pd.testing.assert_frame_equal(
        _le_cutoff(full.values),
        _le_cutoff(truncated.values),
        check_exact=False,
        rtol=1e-9,
        atol=1e-12,
    )
