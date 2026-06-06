"""Tearsheet builder-shape tests: weight parsing, exposure summary, regime
summary, and benchmark comparison output (src/accounting/tearsheet_calculator.py).
"""

import numpy as np
import pandas as pd
import pytest

from src.accounting import tearsheet_calculator as tc

pytestmark = [pytest.mark.unit, pytest.mark.regression]


class TestParseWeights:
    def test_dict_passthrough_as_floats(self):
        assert tc.parse_weights({"TLT": 1, "AGG": 0}) == {"TLT": 1.0, "AGG": 0.0}

    def test_json_string(self):
        assert tc.parse_weights('{"TLT": 0.6, "AGG": 0.4}') == {"TLT": 0.6, "AGG": 0.4}

    def test_python_literal_string(self):
        assert tc.parse_weights("{'TLT': 0.5, 'SHY': 0.5}") == {"TLT": 0.5, "SHY": 0.5}

    @pytest.mark.parametrize("value", [None, float("nan"), "", "   ", "not-weights"])
    def test_unparseable_returns_empty(self, value):
        assert tc.parse_weights(value) == {}


class TestBuildWeightFrame:
    def test_extracts_per_asset_columns(self):
        df = pd.DataFrame(
            {"date": ["2020-01-01"], "scenario_id": ["s1"], "weights": [{"TLT": 0.6, "AGG": 0.4}]}
        )
        out = tc.build_weight_frame(df)
        assert out.loc[0, "TLT"] == pytest.approx(0.6)
        assert out.loc[0, "AGG"] == pytest.approx(0.4)
        assert out.loc[0, "SHY"] == pytest.approx(0.0)  # missing asset defaults to 0

    def test_no_weights_column_returns_empty(self):
        assert tc.build_weight_frame(pd.DataFrame({"date": ["2020-01-01"]})).empty


class TestExposureSummary:
    def _results(self):
        return pd.DataFrame(
            {
                "date": ["2020-01-01", "2020-01-02"],
                "scenario_id": ["s1", "s1"],
                "weights": [
                    {"TLT": 0.6, "AGG": 0.3, "SHY": 0.1},
                    {"TLT": 0.4, "AGG": 0.4, "SHY": 0.2},
                ],
            }
        )

    def test_avg_weights_match_input_means(self):
        summary = dict(
            zip(
                tc.build_exposure_summary(self._results())["metric"],
                tc.build_exposure_summary(self._results())["value"],
            )
        )
        assert summary["avg_weight_TLT"] == pytest.approx(0.5)  # (0.6+0.4)/2
        assert summary["avg_weight_AGG"] == pytest.approx(0.35)
        assert summary["avg_weight_SHY"] == pytest.approx(0.15)
        assert summary["avg_duration_exposure"] == pytest.approx(0.85)  # mean(0.9, 0.8)
        assert summary["avg_defensive_exposure"] == pytest.approx(0.15)

    def test_time_fraction_metrics(self):
        summary = dict(
            zip(
                tc.build_exposure_summary(self._results())["metric"],
                tc.build_exposure_summary(self._results())["value"],
            )
        )
        # Defensive (SHY) never >= 0.5; duration (TLT+AGG) always >= 0.5.
        assert summary["time_mostly_defensive"] == pytest.approx(0.0)
        assert summary["time_mostly_duration_exposed"] == pytest.approx(1.0)

    def test_no_weights_returns_empty(self):
        assert tc.build_exposure_summary(pd.DataFrame({"date": ["2020-01-01"]})).empty


class TestRegimeSummary:
    def _results(self):
        return pd.DataFrame(
            {
                "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
                "scenario_id": ["s1", "s1", "s1"],
                "nav": [101.0, 103.0, 102.0],
                "ret": [0.01, 0.0198, -0.0097],
                "weights": [{"TLT": 0.5, "AGG": 0.5, "SHY": 0.0}] * 3,
            }
        )

    def _regime(self):
        return pd.DataFrame(
            {
                "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
                "scenario_id": ["s1", "s1", "s1"],
                "inflation_regime": ["DIS", "DIS", "INF"],
            }
        )

    def test_merge_aligns_on_date_and_scenario(self):
        merged = tc.merge_regime_trace(self._results(), self._regime()).set_index("date")
        assert merged.loc[pd.Timestamp("2020-01-01"), "inflation_regime"] == "DIS"
        assert merged.loc[pd.Timestamp("2020-01-03"), "inflation_regime"] == "INF"

    def test_unmatched_date_gets_nan(self):
        regime = self._regime().iloc[:1]  # only 2020-01-01
        merged = tc.merge_regime_trace(self._results(), regime).set_index("date")
        assert pd.isna(merged.loc[pd.Timestamp("2020-01-02"), "inflation_regime"])

    def test_regime_summary_groups_by_regime(self):
        summary = tc.build_regime_summary(self._results(), self._regime(), periods_per_year=252)
        assert (summary["regime_type"] == "inflation_regime").all()
        by_regime = summary.set_index("regime")
        assert int(by_regime.loc["DIS", "n_days"]) == 2
        assert int(by_regime.loc["INF", "n_days"]) == 1

    def test_empty_regime_returns_empty(self):
        assert tc.build_regime_summary(self._results(), None, 252).empty


class TestBenchmarkSummary:
    def _benchmark_prices(self, dates):
        frames = []
        for ticker, closes in {
            "TLT": [100.0, 101.0, 102.5, 104.0, 103.0],
            "AGG": [50.0, 50.2, 50.1, 50.3, 50.25],
            "SHY": [80.0, 80.05, 80.1, 80.08, 80.12],
        }.items():
            frames.append(pd.DataFrame({"date": dates, "ticker": ticker, "close": closes}))
        return pd.concat(frames, ignore_index=True)

    def test_output_shape_and_benchmark_names(self):
        dates = pd.bdate_range("2020-01-01", periods=5)
        prices = self._benchmark_prices(dates)
        tlt_ret = pd.Series([100.0, 101.0, 102.5, 104.0, 103.0], index=dates).pct_change().dropna()
        results = pd.DataFrame({"date": dates[1:], "ret": tlt_ret.values, "nav": (1000 * (1 + tlt_ret).cumprod()).values})

        summary = tc.build_benchmark_summary(results, prices, periods_per_year=252)

        assert set(summary["benchmark"]) == {"TLT", "AGG", "SHY", "EqualWeight_TLT_AGG_SHY"}
        assert {"benchmark", "beta", "alpha", "correlation", "tracking_error", "active_cagr"}.issubset(summary.columns)

    def test_strategy_equal_to_benchmark_gives_unit_beta_corr(self):
        dates = pd.bdate_range("2020-01-01", periods=5)
        prices = self._benchmark_prices(dates)
        # Strategy returns set EQUAL to TLT benchmark returns -> beta=corr=1 vs TLT.
        tlt_ret = pd.Series([100.0, 101.0, 102.5, 104.0, 103.0], index=dates).pct_change().dropna()
        results = pd.DataFrame({"date": dates[1:], "ret": tlt_ret.values, "nav": (1000 * (1 + tlt_ret).cumprod()).values})

        summary = tc.build_benchmark_summary(results, prices, periods_per_year=252)
        tlt_row = summary[summary["benchmark"] == "TLT"].iloc[0]
        assert tlt_row["correlation"] == pytest.approx(1.0, abs=1e-9)
        assert tlt_row["beta"] == pytest.approx(1.0, abs=1e-6)

    def test_missing_benchmark_prices_returns_empty(self):
        results = pd.DataFrame({"date": ["2020-01-02"], "ret": [0.01], "nav": [1010.0]})
        assert tc.build_benchmark_summary(results, None, 252).empty
