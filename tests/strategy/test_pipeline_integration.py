"""Decision-pipeline integration: hand-crafted signals -> full Decision.

Drives `orchestrate_decision_pipeline` end-to-end (regime -> favourable -> base ->
conviction -> sizing -> constraints) with no vol/cov estimates, asserting the
regime path and that final weights are a valid long-only fully-invested allocation.
"""

import pytest

from src.decision.models import Decision
from src.engine.decision_orchestration import orchestrate_decision_pipeline

pytestmark = [pytest.mark.integration, pytest.mark.regression]


def _run(price, macro):
    return orchestrate_decision_pipeline(Decision(date="2020-06-01"), price, macro)


def _assert_valid_allocation(decision):
    assert decision.final_weights is not None
    assert sum(decision.final_weights.values()) == pytest.approx(1.0)
    assert all(w >= 0.0 for w in decision.final_weights.values())
    assert decision.gross_exposure == pytest.approx(1.0)


def test_hawkish_bearish_goes_defensive_to_shy(make_price_signals, make_macro_signals):
    macro = make_macro_signals(
        inflation_rising=True,
        real_rate_tight=True,
        growth_slowing=True,
        labor_weakening=True,
        jobless_rising=True,
    )
    decision = _run(make_price_signals(), macro)

    assert decision.regime == "hawkish_bearish"
    assert decision.direction == {"TLT": 0, "AGG": 0, "SHY": 1}
    _assert_valid_allocation(decision)
    assert decision.final_weights["SHY"] == pytest.approx(1.0)


def test_dovish_bullish_favours_duration(make_price_signals, make_macro_signals):
    macro = make_macro_signals(disinflation=True)  # dovish + 0 bearish flags -> bullish
    decision = _run(make_price_signals(), macro)

    assert decision.regime == "dovish_bullish"
    assert decision.direction == {"TLT": 1, "AGG": 1, "SHY": 0}
    assert decision.base_weights == pytest.approx({"TLT": 0.45, "AGG": 0.45, "SHY": 0.10})
    _assert_valid_allocation(decision)
    # Duration sleeve dominates the defensive sleeve.
    assert decision.final_weights["TLT"] + decision.final_weights["AGG"] > decision.final_weights["SHY"]


def test_default_macro_is_neutral_bullish(make_price_signals, make_macro_signals):
    decision = _run(make_price_signals(), make_macro_signals())

    assert decision.regime == "neutral_bullish"
    assert decision.direction == {"TLT": 0, "AGG": 1, "SHY": 1}
    _assert_valid_allocation(decision)
    # TLT not favoured -> zero base weight -> zero final weight.
    assert decision.final_weights["TLT"] == pytest.approx(0.0)


def test_missing_price_signal_falls_back_to_shy(make_price_signals, make_macro_signals):
    price = make_price_signals(tickers=("TLT", "AGG"))  # SHY missing
    decision = _run(price, make_macro_signals())

    assert decision.regime == "data_fallback"
    assert decision.direction == {"TLT": 0, "AGG": 0, "SHY": 1}
    _assert_valid_allocation(decision)
    assert decision.final_weights["SHY"] == pytest.approx(1.0)


def test_pipeline_is_deterministic(make_price_signals, make_macro_signals):
    macro = make_macro_signals(disinflation=True)
    first = _run(make_price_signals(), macro).final_weights
    second = _run(make_price_signals(), macro).final_weights
    assert first == pytest.approx(second)
