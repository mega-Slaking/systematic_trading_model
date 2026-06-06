"""Unit tests for weight-based rebalance trade generation
(src/execution/rebalance_v2.py). Money-critical: ordering, cash limits, thresholds.
"""

import pytest

from src.execution.rebalance_v2 import generate_weight_rebalance_trades
from src.execution.models import ExecutionCosts

pytestmark = pytest.mark.unit


ZERO_COSTS = ExecutionCosts(
    fee_bps={"TLT": 0.0, "AGG": 0.0, "SHY": 0.0},
    slippage_bps={"TLT": 0.0, "AGG": 0.0, "SHY": 0.0},
    min_trade_notional=0.0,
)


def test_buys_from_cash_to_target():
    # All cash, target 100% TLT @ 100, NAV=1000 -> 10 shares.
    trades = generate_weight_rebalance_trades(
        date="d",
        positions={},
        cash_available=1000.0,
        target_weights={"TLT": 1.0},
        prices={"TLT": 100.0},
        costs=ZERO_COSTS,
    )
    assert len(trades) == 1
    assert trades[0].side == "BUY"
    assert trades[0].ticker == "TLT"
    assert trades[0].qty == pytest.approx(10.0)


def test_no_trade_when_already_at_target():
    trades = generate_weight_rebalance_trades(
        date="d",
        positions={"TLT": 10.0},
        cash_available=0.0,
        target_weights={"TLT": 1.0},
        prices={"TLT": 100.0},
        costs=ZERO_COSTS,
    )
    assert trades == []


def test_sell_leg_precedes_buy_leg():
    # Hold AGG, want TLT -> SELL AGG before BUY TLT.
    trades = generate_weight_rebalance_trades(
        date="d",
        positions={"AGG": 20.0},
        cash_available=0.0,
        target_weights={"TLT": 1.0},
        prices={"TLT": 100.0, "AGG": 50.0},
        costs=ZERO_COSTS,
    )
    sides = [t.side for t in trades]
    assert "SELL" in sides and "BUY" in sides
    assert sides.index("SELL") < sides.index("BUY")


def test_below_min_trade_notional_is_skipped():
    costs = ExecutionCosts(
        fee_bps={"TLT": 0.0}, slippage_bps={"TLT": 0.0}, min_trade_notional=1000.0
    )
    # NAV ~1001, target 100% TLT -> ~0.01 share delta = ~$1 notional < $1000 -> skip.
    trades = generate_weight_rebalance_trades(
        date="d",
        positions={"TLT": 10.0},
        cash_available=1.0,
        target_weights={"TLT": 1.0},
        prices={"TLT": 100.0},
        costs=costs,
    )
    assert trades == []


def test_buys_capped_by_available_cash():
    # NAV=500, target wants $500 TLT -> 5 shares (cannot exceed cash).
    trades = generate_weight_rebalance_trades(
        date="d",
        positions={},
        cash_available=500.0,
        target_weights={"TLT": 1.0},
        prices={"TLT": 100.0},
        costs=ZERO_COSTS,
    )
    assert trades[0].qty == pytest.approx(5.0)


def test_drift_tolerance_skips_small_rebalance():
    # Current 100% TLT vs target 99/1 -> half-L1 drift 0.01 < tol 0.05 -> no trades.
    trades = generate_weight_rebalance_trades(
        date="d",
        positions={"TLT": 10.0},
        cash_available=0.0,
        target_weights={"TLT": 0.99, "SHY": 0.01},
        prices={"TLT": 100.0, "SHY": 100.0},
        costs=ZERO_COSTS,
        drift_tol=0.05,
    )
    assert trades == []


def test_nonpositive_nav_returns_empty():
    trades = generate_weight_rebalance_trades(
        date="d",
        positions={},
        cash_available=0.0,
        target_weights={"TLT": 1.0},
        prices={"TLT": 100.0},
        costs=ZERO_COSTS,
    )
    assert trades == []


def test_fees_reduce_buyable_quantity():
    # 100 bps fee -> max_qty = cash / (px * 1.01) < 10 shares; fee_cost > 0.
    costs = ExecutionCosts(
        fee_bps={"TLT": 100.0}, slippage_bps={"TLT": 0.0}, min_trade_notional=0.0
    )
    trades = generate_weight_rebalance_trades(
        date="d",
        positions={},
        cash_available=1000.0,
        target_weights={"TLT": 1.0},
        prices={"TLT": 100.0},
        costs=costs,
    )
    assert trades[0].qty < 10.0
    assert trades[0].fee_cost > 0.0
