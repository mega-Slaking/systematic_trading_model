"""Closed-form sanity checks for tearsheet metrics (src/accounting/tearsheet_calculator.py).

Expected values are computed by hand (not by re-running the function), so these
catch formula regressions rather than tautologically mirroring the code.
"""

import numpy as np
import pandas as pd
import pytest

from src.accounting import tearsheet_calculator as tc

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def _equity(navs):
    return pd.DataFrame(
        {"date": pd.bdate_range("2020-01-01", periods=len(navs)), "nav": navs}
    )


class TestReturnMetrics:
    def test_total_return(self):
        assert tc.compute_total_return(_equity([100.0, 110.0])) == pytest.approx(0.10)

    def test_cagr_two_years_is_geometric(self):
        # +21% over 504 daily periods (2y) -> sqrt(1.21) - 1 = 0.10
        assert tc.compute_cagr(0.21, n_periods=504, periods_per_year=252) == pytest.approx(0.10)

    def test_cagr_zero_periods_is_nan(self):
        assert np.isnan(tc.compute_cagr(0.1, n_periods=0, periods_per_year=252))


class TestVolAndRiskAdjusted:
    def test_annualized_vol_hand_computed(self):
        r = pd.Series([0.01, 0.03])  # std(ddof=1) = 0.0141421356
        assert tc.compute_annualized_volatility(r, 252) == pytest.approx(
            0.0141421356 * np.sqrt(252)
        )

    def test_constant_returns_have_zero_vol(self):
        assert tc.compute_annualized_volatility(pd.Series([0.01, 0.01, 0.01]), 252) == pytest.approx(0.0)

    def test_sharpe_hand_computed_rf_zero(self):
        r = pd.Series([0.01, 0.03])
        expected = (0.02 * 252) / (0.0141421356 * np.sqrt(252))
        assert tc.compute_sharpe(r, 0.0, 252) == pytest.approx(expected)

    def test_sharpe_zero_vol_is_nan(self):
        assert np.isnan(tc.compute_sharpe(pd.Series([0.01, 0.01]), 0.0, 252))

    def test_sortino_uses_downside_only(self):
        r = pd.Series([-0.01, 0.03])  # rf=0 -> excess = r
        downside_dev = np.sqrt(np.mean([(-0.01) ** 2, 0.0])) * np.sqrt(252)
        expected = (r.mean() * 252) / downside_dev
        assert tc.compute_sortino(r, 0.0, 252) == pytest.approx(expected)


class TestDrawdown:
    def test_max_drawdown_peak_to_trough(self):
        dd = tc.compute_drawdown_curve(_equity([100.0, 120.0, 90.0, 130.0]))
        assert tc.compute_max_drawdown(dd) == pytest.approx(-0.25)  # 120 -> 90

    def test_no_drawdown_when_monotonic(self):
        dd = tc.compute_drawdown_curve(_equity([100.0, 110.0, 120.0]))
        assert tc.compute_max_drawdown(dd) == pytest.approx(0.0)

    def test_calmar_is_cagr_over_abs_dd(self):
        assert tc.compute_calmar(0.10, -0.20) == pytest.approx(0.5)

    def test_calmar_zero_drawdown_is_nan(self):
        assert np.isnan(tc.compute_calmar(0.10, 0.0))


class TestVarCvar:
    def test_var_negates_lower_quantile(self):
        r = pd.Series([-0.05, -0.02, 0.0, 0.01, 0.03])
        assert tc.compute_var(r, confidence=0.8) == pytest.approx(-r.quantile(0.2))

    def test_var_positive_when_losses_present(self):
        assert tc.compute_var(pd.Series([-0.10, -0.05, 0.0, 0.02]), 0.9) > 0

    def test_cvar_is_tail_mean(self):
        r = pd.Series([-0.10, -0.08, -0.02, 0.01, 0.05])
        tail = r[r <= r.quantile(0.1)]
        assert tc.compute_cvar(r, 0.9) == pytest.approx(-tail.mean())


class TestTradeQuality:
    def test_daily_hit_rate(self):
        assert tc.compute_daily_hit_rate(pd.Series([0.01, -0.01, 0.02, 0.0])) == pytest.approx(0.5)

    def test_avg_win_and_loss(self):
        r = pd.Series([0.02, 0.04, -0.01, -0.03])
        assert tc.compute_avg_win(r) == pytest.approx(0.03)
        assert tc.compute_avg_loss(r) == pytest.approx(0.02)  # abs(mean of losses)

    def test_payoff_ratio(self):
        r = pd.Series([0.02, 0.04, -0.01, -0.03])
        assert tc.compute_payoff_ratio(r) == pytest.approx(0.03 / 0.02)

    def test_profit_factor(self):
        r = pd.Series([0.02, 0.04, -0.01, -0.03])  # wins 0.06 / |losses| 0.04
        assert tc.compute_profit_factor(r) == pytest.approx(0.06 / 0.04)

    def test_payoff_ratio_no_losses_is_nan(self):
        assert np.isnan(tc.compute_payoff_ratio(pd.Series([0.01, 0.02])))
