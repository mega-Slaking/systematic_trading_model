"""Signal engines: price (src/signals_price) and macro (src/signals_macro).

Asserts derived columns, closed-form derivations, and lookahead safety (a signal
at date t is unchanged when future data is removed).
"""

import pytest

from src.signals_price.price_signal_engine import compute_price_signals
from src.signals_macro.macro_signal_engine import compute_macro_signals

pytestmark = [pytest.mark.unit, pytest.mark.lookahead]


class TestPriceSignals:
    def test_expected_columns(self, synthetic_etf_history):
        out = compute_price_signals(synthetic_etf_history)
        for col in ["daily_ret", "ret_lookback", "ma_short", "ma_long", "trend_up", "ma_slope_z"]:
            assert col in out.columns

    def test_ret_lookback_is_backward_30d_change(self, synthetic_etf_history):
        out = compute_price_signals(synthetic_etf_history)
        tlt = out[out["ticker"] == "TLT"].sort_values("date").reset_index(drop=True)
        # LOOKBACK_DAYS = 30 -> first 30 NaN; value at i = close[i]/close[i-30] - 1
        assert tlt["ret_lookback"].iloc[:30].isna().all()
        i = 50
        expected = tlt["close"].iloc[i] / tlt["close"].iloc[i - 30] - 1.0
        assert tlt["ret_lookback"].iloc[i] == pytest.approx(expected)

    def test_no_lookahead(self, synthetic_etf_history):
        full = compute_price_signals(synthetic_etf_history)
        tlt_full = full[full["ticker"] == "TLT"].sort_values("date").reset_index(drop=True)
        cutoff = tlt_full["date"].iloc[120]

        truncated = compute_price_signals(
            synthetic_etf_history[synthetic_etf_history["date"] <= cutoff]
        )
        tlt_trunc = truncated[truncated["ticker"] == "TLT"].sort_values("date").reset_index(drop=True)

        assert tlt_trunc["ret_lookback"].iloc[-1] == pytest.approx(tlt_full["ret_lookback"].iloc[120])


class TestMacroSignals:
    def test_yield_curve_and_expected_columns(self, synthetic_macro_history):
        out = compute_macro_signals(synthetic_macro_history)
        assert (out["yield_curve"] == out["gs10"] - out["gs2"]).all()
        for col in [
            "cpi_yoy",
            "disinflation",
            "inflation_rising",
            "growth_slowing",
            "curve_inverted",
            "macro_supports_duration",
            "real_policy_rate",
        ]:
            assert col in out.columns

    def test_cpi_yoy_is_12_period_change(self, synthetic_macro_history):
        out = compute_macro_signals(synthetic_macro_history).sort_values("date").reset_index(drop=True)
        i = 15
        expected = out["cpi"].iloc[i] / out["cpi"].iloc[i - 12] - 1.0
        assert out["cpi_yoy"].iloc[i] == pytest.approx(expected)

    def test_curve_inverted_matches_sign(self, synthetic_macro_history):
        out = compute_macro_signals(synthetic_macro_history)
        assert (out["curve_inverted"] == (out["yield_curve"] < 0)).all()
