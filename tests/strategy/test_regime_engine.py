"""Regime classifier truth tables and the missing-price fallback
(src/decision/regime_engine.py).
"""

import pandas as pd
import pytest

from src.decision.models import Decision
from src.decision.regime_engine import (
    _classify_monetary_regime,
    _classify_economic_regime,
    evaluate_regime,
)

pytestmark = pytest.mark.unit


def _macro_row(**kw):
    base = dict(
        disinflation=False,
        inflation_rising=False,
        real_rate_tight=False,
        fed_funds_direction=0,
        growth_slowing=False,
        labor_weakening=False,
        jobless_rising=False,
        credit_spread_widening=False,
        confidence_low=False,
    )
    base.update(kw)
    return pd.Series(base)


class TestMonetaryRegime:
    def test_disinflation_without_tight_rates_is_dovish(self):
        assert _classify_monetary_regime(_macro_row(disinflation=True)) == "dovish"

    def test_inflation_rising_with_tight_rates_is_hawkish(self):
        assert _classify_monetary_regime(
            _macro_row(inflation_rising=True, real_rate_tight=True)
        ) == "hawkish"

    def test_easing_with_disinflation_is_dovish(self):
        # disinflation but real_rate_tight -> first branch fails; fed cut path -> dovish
        assert _classify_monetary_regime(
            _macro_row(disinflation=True, real_rate_tight=True, fed_funds_direction=-1)
        ) == "dovish"

    def test_hiking_with_inflation_is_hawkish(self):
        assert _classify_monetary_regime(
            _macro_row(inflation_rising=True, fed_funds_direction=1)
        ) == "hawkish"

    def test_quiet_macro_is_neutral(self):
        assert _classify_monetary_regime(_macro_row()) == "neutral"


class TestEconomicRegime:
    def test_three_or_more_bearish_flags_is_bearish(self):
        assert _classify_economic_regime(
            _macro_row(growth_slowing=True, labor_weakening=True, jobless_rising=True)
        ) == "bearish"

    def test_zero_bearish_flags_is_bullish(self):
        assert _classify_economic_regime(_macro_row()) == "bullish"

    @pytest.mark.parametrize("flags", [
        {"growth_slowing": True},
        {"growth_slowing": True, "labor_weakening": True},
    ])
    def test_one_or_two_flags_is_neutral(self, flags):
        assert _classify_economic_regime(_macro_row(**flags)) == "neutral"


def test_missing_price_signal_triggers_data_fallback(make_macro_signals):
    # Price signals frame missing SHY -> a ticker has no latest row -> fallback.
    price = pd.DataFrame(
        [
            {"date": pd.Timestamp("2020-06-01"), "ticker": "TLT",
             "ret_lookback": 0.01, "trend_up": True, "ma_slope_z": 0.3},
            {"date": pd.Timestamp("2020-06-01"), "ticker": "AGG",
             "ret_lookback": 0.01, "trend_up": True, "ma_slope_z": 0.3},
        ]
    )
    out = evaluate_regime(Decision(date="2020-06-01"), price, make_macro_signals())
    assert out.regime == "data_fallback"
    assert out.rule_id == "DATA_FALLBACK_001"
    assert out.direction == {"TLT": 0, "AGG": 0, "SHY": 1}
