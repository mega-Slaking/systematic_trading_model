"""Portfolio accounting/execution mechanics (src/backtest/portfolio.py).

Production fees/slippage are 0 (config.py), so NAV is conserved across a pure
rebalance — these tests assert exactly that, plus compounding and weight sums.
"""

import pytest

from src.backtest.portfolio import Portfolio
from src.decision.models import Decision

pytestmark = pytest.mark.integration

PRICES = {"TLT": 100.0, "AGG": 50.0, "SHY": 80.0}


def _decision(weights):
    return Decision(date="d", final_weights=weights, reason="test")


def test_nav_starts_at_initial_capital():
    p = Portfolio(1_000_000.0)
    assert p.nav == 1_000_000.0
    p.mark_to_market(PRICES)
    assert p.nav == 1_000_000.0  # all cash, no holdings


def test_full_investment_from_cash_conserves_nav():
    p = Portfolio(1000.0)
    p.rebalance_v2(_decision({"TLT": 1.0}), PRICES, "d1")
    p.mark_to_market(PRICES)
    assert p.holdings["TLT"] == pytest.approx(10.0)
    assert p.cash == pytest.approx(0.0)
    assert p.nav == pytest.approx(1000.0)  # zero costs -> conserved


def test_nav_tracks_price_change():
    p = Portfolio(1000.0)
    p.rebalance_v2(_decision({"TLT": 1.0}), {"TLT": 100.0}, "d1")  # 10 shares
    p.mark_to_market({"TLT": 110.0})
    assert p.nav == pytest.approx(1100.0)


def test_returns_compound_over_periods():
    p = Portfolio(1000.0)
    p.rebalance_v2(_decision({"TLT": 1.0}), {"TLT": 100.0}, "d1")
    p.mark_to_market({"TLT": 110.0})  # +10% -> 1100
    p.mark_to_market({"TLT": 121.0})  # +10% -> 1210
    assert p.nav == pytest.approx(1210.0)


def test_realized_weights_sum_to_one_after_full_rebalance():
    p = Portfolio(1000.0)
    p.rebalance_v2(_decision({"TLT": 0.5, "AGG": 0.3, "SHY": 0.2}), PRICES, "d1")
    p.mark_to_market(PRICES)

    realized = {t: p.holdings.get(t, 0.0) * PRICES[t] / p.nav for t in PRICES}
    assert sum(realized.values()) == pytest.approx(1.0)
    assert realized["TLT"] == pytest.approx(0.5, abs=1e-6)
    assert realized["AGG"] == pytest.approx(0.3, abs=1e-6)


def test_rebalance_between_assets_updates_holdings():
    p = Portfolio(1000.0)
    p.rebalance_v2(_decision({"TLT": 1.0}), PRICES, "d1")
    p.rebalance_v2(_decision({"AGG": 1.0}), PRICES, "d2")  # rotate TLT -> AGG
    p.mark_to_market(PRICES)
    assert p.holdings.get("TLT", 0.0) == pytest.approx(0.0)
    assert p.holdings["AGG"] == pytest.approx(20.0)  # 1000 / 50
    assert p.nav == pytest.approx(1000.0)
