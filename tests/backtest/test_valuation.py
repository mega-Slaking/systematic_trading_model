"""Unit tests for portfolio valuation (src/accounting/valuation.py)."""

import pytest

from src.accounting.valuation import value_portfolio

pytestmark = pytest.mark.unit


def test_nav_is_cash_plus_holdings_value():
    snap = value_portfolio(
        date="2020-01-01",
        cash=1000.0,
        holdings={"TLT": 10.0, "AGG": 5.0},
        prices={"TLT": 100.0, "AGG": 50.0},
    )
    assert snap.nav == pytest.approx(1000.0 + 10 * 100 + 5 * 50)  # 2250
    assert snap.cash == 1000.0
    assert snap.date == "2020-01-01"


def test_empty_holdings_nav_is_cash():
    snap = value_portfolio(date="d", cash=500.0, holdings={}, prices={})
    assert snap.nav == 500.0


def test_zero_units_contribute_nothing():
    snap = value_portfolio(
        date="d", cash=100.0, holdings={"TLT": 0.0}, prices={"TLT": 100.0}
    )
    assert snap.nav == 100.0


def test_missing_price_raises_keyerror():
    with pytest.raises(KeyError):
        value_portfolio(date="d", cash=0.0, holdings={"TLT": 1.0}, prices={"AGG": 10.0})


def test_snapshot_copies_inputs_defensively():
    holdings = {"TLT": 1.0}
    prices = {"TLT": 100.0}
    snap = value_portfolio(date="d", cash=0.0, holdings=holdings, prices=prices)

    holdings["TLT"] = 999.0
    prices["TLT"] = 999.0

    assert snap.holdings["TLT"] == 1.0
    assert snap.prices["TLT"] == 100.0
    assert snap.nav == pytest.approx(100.0)
