"""Decision-pipeline integration: hand-crafted signals -> full Decision.

Drives `orchestrate_decision_pipeline` end-to-end (regime -> legacy table ->
TLT tracker -> sizing -> constraints) with no vol/cov estimates, asserting the
regime path still classifies and that final weights are a valid long-only
fully-invested allocation.

NOTE: the live pipeline now runs the TLT-tracking allocator
(`src/strategy/tlt_tracker.py`), not the old regime-table path. With only a
one-row price snapshot the tracker cannot confirm a trend (it needs
`entry_confirm_days` of history) so it returns its NEUTRAL base allocation. The
regime->direction->base-table behavior that used to be asserted here is now
covered directly by the moved unit tests (tests/strategy/test_favourable_assets.py
and test_base_allocator.py). The old assertions are preserved, commented, at the
bottom of this file as a rollback reference.
"""

import pytest

from src.decision.models import Decision
from src.engine.decision_orchestration import orchestrate_decision_pipeline

pytestmark = [pytest.mark.integration, pytest.mark.regression]

# TLT tracker NEUTRAL base on a single snapshot (TLT=tlt_neutral, SHY=shy_min).
NEUTRAL_BASE = {"TLT": 0.40, "AGG": 0.55, "SHY": 0.05}


def _run(price, macro):
    return orchestrate_decision_pipeline(Decision(date="2020-06-01"), price, macro)


def _assert_valid_allocation(decision):
    assert decision.final_weights is not None
    assert sum(decision.final_weights.values()) == pytest.approx(1.0)
    assert all(w >= 0.0 for w in decision.final_weights.values())
    assert decision.gross_exposure == pytest.approx(1.0)


def test_single_snapshot_yields_neutral_tracker_allocation(make_price_signals, make_macro_signals):
    decision = _run(make_price_signals(), make_macro_signals())

    # Regime classification still runs (it just no longer drives direction).
    assert decision.regime == "neutral_bullish"
    # One snapshot -> no confirmed trend -> tracker NEUTRAL base.
    assert decision.base_weights == pytest.approx(NEUTRAL_BASE)
    _assert_valid_allocation(decision)


def test_hawkish_bearish_still_classified_and_valid(make_price_signals, make_macro_signals):
    macro = make_macro_signals(
        inflation_rising=True,
        real_rate_tight=True,
        growth_slowing=True,
        labor_weakening=True,
        jobless_rising=True,
    )
    decision = _run(make_price_signals(), macro)

    assert decision.regime == "hawkish_bearish"
    # Macro veto caps TLT at macro_veto_tlt_cap (0.40); NEUTRAL is already there,
    # so the base is unchanged but TLT never exceeds the cap.
    assert decision.base_weights["TLT"] <= 0.40 + 1e-9
    assert decision.base_weights == pytest.approx(NEUTRAL_BASE)
    _assert_valid_allocation(decision)


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


# ---------------------------------------------------------------------------
# OLD regime-table pipeline assertions (pre-TLT-tracker). Kept commented as a
# rollback reference (project convention). These asserted the modern path
# regime -> direction -> base table, which now lives in src/legacy/ and is
# unit-tested directly. They will NOT pass against the TLT-tracker pipeline.
# ---------------------------------------------------------------------------
# def test_hawkish_bearish_goes_defensive_to_shy(make_price_signals, make_macro_signals):
#     macro = make_macro_signals(
#         inflation_rising=True, real_rate_tight=True, growth_slowing=True,
#         labor_weakening=True, jobless_rising=True,
#     )
#     decision = _run(make_price_signals(), macro)
#     assert decision.regime == "hawkish_bearish"
#     assert decision.direction == {"TLT": 0, "AGG": 0, "SHY": 1}
#     _assert_valid_allocation(decision)
#     assert decision.final_weights["SHY"] == pytest.approx(1.0)
#
# def test_dovish_bullish_favours_duration(make_price_signals, make_macro_signals):
#     macro = make_macro_signals(disinflation=True)  # dovish + 0 bearish flags -> bullish
#     decision = _run(make_price_signals(), macro)
#     assert decision.regime == "dovish_bullish"
#     assert decision.direction == {"TLT": 1, "AGG": 1, "SHY": 0}
#     assert decision.base_weights == pytest.approx({"TLT": 0.45, "AGG": 0.45, "SHY": 0.10})
#     _assert_valid_allocation(decision)
#     assert decision.final_weights["TLT"] + decision.final_weights["AGG"] > decision.final_weights["SHY"]
#
# def test_default_macro_is_neutral_bullish(make_price_signals, make_macro_signals):
#     decision = _run(make_price_signals(), make_macro_signals())
#     assert decision.regime == "neutral_bullish"
#     assert decision.direction == {"TLT": 0, "AGG": 1, "SHY": 1}
#     _assert_valid_allocation(decision)
#     assert decision.final_weights["TLT"] == pytest.approx(0.0)
