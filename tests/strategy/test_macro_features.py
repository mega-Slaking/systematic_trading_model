"""Macro-feature derivations (src/signals_macro/macro_features.py).

Covers the Phase-1 compute layer from docs/macro_data_interpretability.md:
closed-form derivation checks, the **engine-equality pin** (the dashboard's
formulas must match macro_signal_engine — resolved decision #3), units sanity
(YoY stays a decimal fraction, not × 100), look-ahead safety, and input
validation.
"""

import pandas as pd
import pytest

from src.signals_macro.macro_features import (
    CURVE_REGIMES,
    MACRO_REGIMES,
    build_conditional_forward_return_table,
    classify_curve_regime,
    classify_macro_regime,
    compute_activity_features,
    compute_cpi_features,
    compute_curve_regime,
    compute_forward_returns,
    compute_labour_features,
    compute_macro_regime,
    compute_policy_features,
    compute_yield_curve_features,
    derive_macro_features,
    inversion_intervals,
    macro_availability_dates,
)
from src.signals_macro.macro_signal_engine import compute_macro_signals

pytestmark = [pytest.mark.unit, pytest.mark.lookahead]


# --------------------------------------------------------------------------- #
# Closed-form derivation checks
# --------------------------------------------------------------------------- #
class TestCpiFeatures:
    def test_cpi_yoy_is_12_period_pct_change(self, synthetic_macro_history):
        cpi = synthetic_macro_history["cpi"]
        out = compute_cpi_features(cpi)
        i = 15
        expected = cpi.iloc[i] / cpi.iloc[i - 12] - 1.0
        assert out["cpi_yoy"].iloc[i] == pytest.approx(expected)
        # First 12 rows have no 12-month lookback.
        assert out["cpi_yoy"].iloc[:12].isna().all()

    def test_change_3m_and_acceleration_are_differences_of_yoy(self, synthetic_macro_history):
        out = compute_cpi_features(synthetic_macro_history["cpi"])
        yoy = out["cpi_yoy"]
        pd.testing.assert_series_equal(out["cpi_yoy_change_3m"], yoy.diff(3), check_names=False)
        pd.testing.assert_series_equal(out["cpi_yoy_acceleration"], yoy.diff().diff(), check_names=False)

    def test_yoy_is_decimal_fraction_not_percent(self, synthetic_macro_history):
        # Guards the deliberate "no × 100" decision: the synthetic CPI drifts a
        # few percent a year, so YoY must be ~0.0x, never ~3.x.
        out = compute_cpi_features(synthetic_macro_history["cpi"])
        assert out["cpi_yoy"].abs().max() < 1.0


class TestActivityFeatures:
    def test_level_passthrough_and_3m_change(self, synthetic_macro_history):
        cfnai = synthetic_macro_history["pmi"]  # the mislabelled CFNAI column
        out = compute_activity_features(cfnai)
        pd.testing.assert_series_equal(out["activity_level"], cfnai.astype("float64"), check_names=False)
        pd.testing.assert_series_equal(out["activity_change_3m"], cfnai.diff(3), check_names=False)


class TestLabourFeatures:
    def test_changes_and_off_the_lows(self, synthetic_macro_history):
        u = synthetic_macro_history["unemployment"]
        out = compute_labour_features(u)
        pd.testing.assert_series_equal(out["unemployment_change_3m"], u.diff(3), check_names=False)
        pd.testing.assert_series_equal(out["unemployment_change_6m"], u.diff(6), check_names=False)
        expected_low = u - u.rolling(window=12, min_periods=12).min()
        pd.testing.assert_series_equal(out["unemployment_minus_12m_low"], expected_low, check_names=False)
        # "off the lows" is non-negative by construction (level >= its trailing min).
        assert (out["unemployment_minus_12m_low"].dropna() >= 0).all()


class TestPolicyFeatures:
    def test_real_policy_rate_uses_core_yoy_in_percentage_points(self, synthetic_macro_history):
        ff = synthetic_macro_history["fed_funds"]
        core_yoy = compute_cpi_features(synthetic_macro_history["core_cpi"])["cpi_yoy"]
        out = compute_policy_features(ff, core_yoy)
        expected = ff - (core_yoy * 100)
        pd.testing.assert_series_equal(out["real_policy_rate"], expected, check_names=False)
        pd.testing.assert_series_equal(out["fed_funds_change_3m"], ff.diff(3), check_names=False)


class TestYieldCurveFeatures:
    def test_spread_and_changes(self, synthetic_macro_history):
        gs2 = synthetic_macro_history["gs2"]
        gs10 = synthetic_macro_history["gs10"]
        out = compute_yield_curve_features(gs2, gs10)
        pd.testing.assert_series_equal(out["curve_spread"], gs10 - gs2, check_names=False)
        pd.testing.assert_series_equal(out["yield_2y_change_3m"], gs2.diff(3), check_names=False)
        pd.testing.assert_series_equal(out["yield_10y_change_1m"], gs10.diff(1), check_names=False)
        pd.testing.assert_series_equal(out["curve_spread_change_3m"], (gs10 - gs2).diff(3), check_names=False)


# --------------------------------------------------------------------------- #
# Orchestrator + the engine-equality pin (decision #3)
# --------------------------------------------------------------------------- #
class TestDeriveMacroFeatures:
    def test_expected_columns_and_date_sorted(self, synthetic_macro_history):
        out = derive_macro_features(synthetic_macro_history)
        for col in [
            "date", "cpi_yoy", "cpi_yoy_change_3m", "cpi_yoy_acceleration",
            "core_cpi_yoy", "activity_level", "activity_change_3m",
            "unemployment_change_3m", "unemployment_minus_12m_low",
            "fed_funds_change_3m", "real_policy_rate",
            "curve_spread", "yield_10y_change_3m", "curve_spread_change_3m",
        ]:
            assert col in out.columns, col
        assert out["date"].is_monotonic_increasing
        assert len(out) == len(synthetic_macro_history)

    def test_does_not_mutate_input(self, synthetic_macro_history):
        before = synthetic_macro_history.copy()
        derive_macro_features(synthetic_macro_history)
        pd.testing.assert_frame_equal(synthetic_macro_history, before)

    def test_matches_engine_on_shared_derivations(self, synthetic_macro_history):
        """The pin: every overlapping derivation equals macro_signal_engine's."""
        features = derive_macro_features(synthetic_macro_history)
        engine = compute_macro_signals(synthetic_macro_history)  # already date-sorted, index reset

        pd.testing.assert_series_equal(features["cpi_yoy"], engine["cpi_yoy"], check_names=False)
        pd.testing.assert_series_equal(features["core_cpi_yoy"], engine["core_cpi_yoy"], check_names=False)
        pd.testing.assert_series_equal(features["real_policy_rate"], engine["real_policy_rate"], check_names=False)
        pd.testing.assert_series_equal(features["cpi_yoy_acceleration"], engine["cpi_yoy_acceleration"], check_names=False)
        # The engine calls the spread `yield_curve`; it is the same quantity.
        pd.testing.assert_series_equal(features["curve_spread"], engine["yield_curve"], check_names=False)

    def test_missing_column_raises(self, synthetic_macro_history):
        with pytest.raises(ValueError, match="missing required column"):
            derive_macro_features(synthetic_macro_history.drop(columns=["core_cpi"]))

    def test_unsorted_input_is_sorted_before_derivation(self, synthetic_macro_history):
        shuffled = synthetic_macro_history.sample(frac=1.0, random_state=1)
        out = derive_macro_features(shuffled)
        assert out["date"].is_monotonic_increasing
        # Derivation on the sorted frame must match the canonical (already-sorted) run.
        canonical = derive_macro_features(synthetic_macro_history)
        pd.testing.assert_frame_equal(out, canonical)


# --------------------------------------------------------------------------- #
# Look-ahead safety: a feature at date t is unchanged when future rows vanish.
# --------------------------------------------------------------------------- #
class TestNoLookahead:
    def test_features_at_t_independent_of_future(self, synthetic_macro_history):
        full = derive_macro_features(synthetic_macro_history)
        cutoff_idx = 20
        cutoff_date = full["date"].iloc[cutoff_idx]

        truncated = derive_macro_features(
            synthetic_macro_history[synthetic_macro_history["date"] <= cutoff_date]
        )
        for col in ["cpi_yoy", "core_cpi_yoy", "real_policy_rate", "curve_spread", "unemployment_minus_12m_low"]:
            assert truncated[col].iloc[-1] == pytest.approx(full[col].iloc[cutoff_idx], nan_ok=True)


# --------------------------------------------------------------------------- #
# Yield-curve regime classification (Phase 2)
# --------------------------------------------------------------------------- #
class TestClassifyCurveRegime:
    def test_four_canonical_regimes(self):
        # (Δ2y, Δ10y): steepening ⟺ Δ10y > Δ2y; bull = both falling, bear = both rising.
        assert classify_curve_regime(-0.5, -0.2) == "Bull steepening"   # 2Y falls more
        assert classify_curve_regime(-0.2, -0.5) == "Bull flattening"   # 10Y falls more
        assert classify_curve_regime(0.2, 0.5) == "Bear steepening"     # 10Y rises more
        assert classify_curve_regime(0.5, 0.2) == "Bear flattening"     # 2Y rises more

    def test_opposite_moves_are_mixed(self):
        assert classify_curve_regime(-0.3, 0.3) == "Mixed"
        assert classify_curve_regime(0.3, -0.3) == "Mixed"

    def test_parallel_shift_classified_as_flattening(self):
        # Equal moves are not strictly steepening (Δ10y > Δ2y is False).
        assert classify_curve_regime(-0.3, -0.3) == "Bull flattening"
        assert classify_curve_regime(0.3, 0.3) == "Bear flattening"


class TestComputeCurveRegime:
    def test_codes_labels_and_incomplete_lookback(self):
        # lookback=1: row i compares to row i-1. Row 0 has no lookback -> NaN/None.
        gs2 = pd.Series([2.0, 1.5, 2.0])   # Δ: -, -0.5, +0.5
        gs10 = pd.Series([3.0, 2.8, 3.0])  # Δ: -, -0.2, +0.2
        out = compute_curve_regime(gs2, gs10, lookback=1)
        assert pd.isna(out["curve_regime_code"].iloc[0]) and out["curve_regime"].iloc[0] is None
        # i=1: both fell, 2Y fell more -> Bull steepening
        assert out["curve_regime"].iloc[1] == "Bull steepening"
        assert out["curve_regime_code"].iloc[1] == float({v: k for k, v in CURVE_REGIMES.items()}["Bull steepening"])
        # i=2: both rose, 10Y rose more (0.2 > 0.5? no) -> 2Y rose more -> Bear flattening
        assert out["curve_regime"].iloc[2] == "Bear flattening"

    def test_index_preserved(self, synthetic_macro_history):
        out = compute_curve_regime(synthetic_macro_history["gs2"], synthetic_macro_history["gs10"])
        assert out.index.equals(synthetic_macro_history.index)
        assert set(out["curve_regime"].dropna().unique()) <= set(CURVE_REGIMES.values())


class TestInversionIntervals:
    def test_contiguous_negative_spans(self):
        dates = pd.to_datetime(["2020-01-01", "2020-02-01", "2020-03-01", "2020-04-01", "2020-05-01"])
        spread = pd.Series([0.5, -0.1, -0.2, 0.3, -0.4])
        spans = inversion_intervals(pd.Series(dates), spread)
        assert spans == [
            {"start": "2020-02-01", "end": "2020-03-01"},
            {"start": "2020-05-01", "end": "2020-05-01"},
        ]

    def test_no_inversion_returns_empty(self):
        dates = pd.to_datetime(["2020-01-01", "2020-02-01"])
        spans = inversion_intervals(pd.Series(dates), pd.Series([0.5, 0.3]))
        assert spans == []


# --------------------------------------------------------------------------- #
# Macro-regime classification (Phase 4)
# --------------------------------------------------------------------------- #
class TestClassifyMacroRegime:
    # A baseline of benign inputs; each test overrides the discriminating fields.
    BASE = dict(
        cpi_yoy=0.02, cpi_yoy_change_3m=0.0, activity_level=0.3, activity_change_3m=0.1,
        unemployment_change_3m=0.0, fed_funds_change_3m=0.0, real_policy_rate=0.0, yield_2y_change_3m=0.0,
    )

    def test_stagflation_risk(self):
        out = classify_macro_regime(**{**self.BASE, "cpi_yoy": 0.05, "cpi_yoy_change_3m": 0.002,
                                       "activity_level": -0.5, "fed_funds_change_3m": 0.0})
        assert out == "Stagflation Risk"

    def test_inflationary_tightening(self):
        out = classify_macro_regime(**{**self.BASE, "cpi_yoy": 0.04, "cpi_yoy_change_3m": 0.003,
                                       "activity_level": 0.3, "activity_change_3m": 0.1,
                                       "fed_funds_change_3m": 0.25, "real_policy_rate": 1.0})
        assert out == "Inflationary Tightening"

    def test_easing_transition(self):
        out = classify_macro_regime(**{**self.BASE, "cpi_yoy": 0.02, "cpi_yoy_change_3m": -0.002,
                                       "fed_funds_change_3m": -0.25, "yield_2y_change_3m": -0.3})
        assert out == "Easing Transition"

    def test_disinflationary_slowdown(self):
        out = classify_macro_regime(**{**self.BASE, "cpi_yoy": 0.025, "cpi_yoy_change_3m": -0.002,
                                       "activity_level": -0.3, "fed_funds_change_3m": 0.0})
        assert out == "Disinflationary Slowdown"

    def test_stable_growth_is_the_fallthrough(self):
        assert classify_macro_regime(**self.BASE) == "Stable Growth"


class TestComputeMacroRegime:
    def test_labels_valid_and_insufficient_is_none(self, synthetic_macro_history):
        features = derive_macro_features(synthetic_macro_history)
        out = compute_macro_regime(features)
        assert out.index.equals(features.index)
        # First rows lack a 12-month cpi_yoy → insufficient → None/NaN.
        assert out["macro_regime"].iloc[0] is None
        assert pd.isna(out["macro_regime_code"].iloc[0])
        # Any classified rows use only the canonical labels.
        assert set(out["macro_regime"].dropna().unique()) <= set(MACRO_REGIMES.values())

    def test_code_label_consistency(self, synthetic_macro_history):
        features = derive_macro_features(synthetic_macro_history)
        out = compute_macro_regime(features)
        code_to_label = MACRO_REGIMES
        for code, label in zip(out["macro_regime_code"], out["macro_regime"]):
            if label is None:
                continue
            assert code_to_label[int(code)] == label


# --------------------------------------------------------------------------- #
# Conditional forward-return analysis (Phase 5)
# --------------------------------------------------------------------------- #
class TestComputeForwardReturns:
    def test_forward_return_is_future_over_horizon(self):
        prices = pd.Series([100.0, 110.0, 121.0, 133.1])  # +10% each step
        out = compute_forward_returns(prices, {"1": 1, "2": 2})
        assert out["1"].iloc[0] == pytest.approx(0.10)   # 110/100 - 1
        assert out["2"].iloc[0] == pytest.approx(0.21)   # 121/100 - 1
        # The tail has no full horizon ahead → NaN (no lookahead beyond the data).
        assert pd.isna(out["1"].iloc[-1])
        assert pd.isna(out["2"].iloc[-1]) and pd.isna(out["2"].iloc[-2])


class TestMacroAvailabilityDates:
    def test_reference_month_end_plus_one_month(self):
        avail = macro_availability_dates(pd.Series(pd.to_datetime(["2024-03-01", "2024-12-01"])))
        assert list(avail.dt.strftime("%Y-%m-%d")) == ["2024-04-30", "2025-01-31"]


class TestConditionalForwardReturnTable:
    def test_per_regime_mean_median_hit_count(self):
        df = pd.DataFrame(
            {
                "regime": ["A", "A", "A", "B", "B"],
                "fwd": [0.02, -0.01, 0.03, -0.04, None],
            }
        )
        out = build_conditional_forward_return_table(df, "regime", ["fwd"]).set_index("regime")
        assert out.loc["A", "n"] == 3
        assert out.loc["A", "fwd_count"] == 3
        assert out.loc["A", "fwd_mean"] == pytest.approx((0.02 - 0.01 + 0.03) / 3)
        assert out.loc["A", "fwd_median"] == pytest.approx(0.02)
        assert out.loc["A", "fwd_hit"] == pytest.approx(2 / 3)  # two of three positive
        # Regime B: one NaN dropped → count 1 (but n counts all conditioning rows).
        assert out.loc["B", "n"] == 2 and out.loc["B", "fwd_count"] == 1
        assert out.loc["B", "fwd_hit"] == pytest.approx(0.0)
