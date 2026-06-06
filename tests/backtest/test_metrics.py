"""Unit tests for daily metrics (src/accounting/metrics.py)."""

import pytest

from src.accounting.metrics import compute_day_metrics
from src.execution.models import Trade

pytestmark = pytest.mark.unit


def _trade(notional_mid=0.0, fee_cost=0.0, slippage_cost=0.0):
    """Minimal Trade for metric aggregation tests (only the summed fields matter)."""
    return Trade(
        date="d",
        ticker="TLT",
        side="BUY",
        qty=1.0,
        price_mid=1.0,
        price_exec=1.0,
        notional_mid=notional_mid,
        notional_exec=notional_mid,
        slippage_bps=0.0,
        fee_bps=0.0,
        slippage_cost=slippage_cost,
        fee_cost=fee_cost,
        total_cost=slippage_cost + fee_cost,
    )


def test_return_computed_from_prev_nav():
    m = compute_day_metrics(date="d", nav=110.0, nav_prev=100.0, trades=[])
    assert m.ret == pytest.approx(0.10)


def test_return_zero_when_no_prev_nav():
    m = compute_day_metrics(date="d", nav=110.0, nav_prev=None, trades=[])
    assert m.ret == 0.0


def test_return_zero_when_prev_nav_nonpositive():
    m = compute_day_metrics(date="d", nav=110.0, nav_prev=0.0, trades=[])
    assert m.ret == 0.0


def test_costs_and_notional_aggregated():
    trades = [
        _trade(notional_mid=100.0, fee_cost=1.0, slippage_cost=0.5),
        _trade(notional_mid=-50.0, fee_cost=0.5, slippage_cost=0.25),
    ]
    m = compute_day_metrics(date="d", nav=100.0, nav_prev=100.0, trades=trades)
    assert m.fee_cost == pytest.approx(1.5)
    assert m.slippage_cost == pytest.approx(0.75)
    assert m.total_cost == pytest.approx(2.25)
    assert m.gross_trade_notional == pytest.approx(150.0)  # abs sum, not net


def test_turnover_uses_prev_nav_denominator():
    m = compute_day_metrics(
        date="d", nav=100.0, nav_prev=200.0, trades=[_trade(notional_mid=50.0)]
    )
    assert m.turnover == pytest.approx(50.0 / 200.0)


def test_turnover_falls_back_to_nav_when_no_prev():
    m = compute_day_metrics(
        date="d", nav=100.0, nav_prev=None, trades=[_trade(notional_mid=50.0)]
    )
    assert m.turnover == pytest.approx(0.5)
