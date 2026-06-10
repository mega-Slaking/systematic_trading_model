"""Exhaustive active-set -> base-weight table (src/legacy/base_allocator_engine.py).
Locks the base allocation rules and rule_ids. (Moved to src/legacy/ when the
TLT-tracking allocator replaced the modern regime-table path.)
"""

import pytest

from src.decision.models import Decision
from src.legacy.base_allocator_engine import allocate_base_weights

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def _decision(direction, regime="dovish_neutral", missing_prices=False):
    return Decision(
        date="d",
        regime=regime,
        direction=direction,
        price_state={"missing_prices": missing_prices},
    )


# (direction active-set, expected base_weights, expected rule_id)
ACTIVE_SET_CASES = [
    ({"TLT": 1, "AGG": 1, "SHY": 0}, {"TLT": 0.45, "AGG": 0.45, "SHY": 0.10}, "BASE_TLT_AGG_001"),
    ({"TLT": 0, "AGG": 1, "SHY": 1}, {"TLT": 0.00, "AGG": 0.50, "SHY": 0.50}, "BASE_AGG_SHY_001"),
    ({"TLT": 1, "AGG": 1, "SHY": 1}, {"TLT": 0.33, "AGG": 0.34, "SHY": 0.33}, "BASE_ALL_ON_001"),
    ({"TLT": 1, "AGG": 0, "SHY": 0}, {"TLT": 0.80, "AGG": 0.20, "SHY": 0.00}, "BASE_TLT_ONLY_001"),
    ({"TLT": 0, "AGG": 1, "SHY": 0}, {"TLT": 0.00, "AGG": 0.85, "SHY": 0.15}, "BASE_AGG_ONLY_001"),
    ({"TLT": 0, "AGG": 0, "SHY": 1}, {"TLT": 0.00, "AGG": 0.00, "SHY": 1.00}, "BASE_SHY_ONLY_001"),
    # Unhandled combos -> defensive default.
    ({"TLT": 1, "AGG": 0, "SHY": 1}, {"TLT": 0.00, "AGG": 0.25, "SHY": 0.75}, "BASE_DEFENSIVE_DEFAULT_001"),
    ({"TLT": 0, "AGG": 0, "SHY": 0}, {"TLT": 0.00, "AGG": 0.25, "SHY": 0.75}, "BASE_DEFENSIVE_DEFAULT_001"),
]


@pytest.mark.parametrize("direction,expected_weights,expected_rule", ACTIVE_SET_CASES)
def test_active_set_maps_to_base_weights(direction, expected_weights, expected_rule):
    out = allocate_base_weights(_decision(direction))
    assert out.base_weights == pytest.approx(expected_weights)
    assert out.rule_id == expected_rule


def test_data_fallback_regime_forces_shy():
    out = allocate_base_weights(
        _decision({"TLT": 1, "AGG": 1, "SHY": 0}, regime="data_fallback")
    )
    assert out.base_weights == {"TLT": 0.0, "AGG": 0.0, "SHY": 1.0}
    assert out.rule_id == "BASE_DATA_FALLBACK_SHY_001"


def test_missing_prices_flag_forces_shy():
    out = allocate_base_weights(
        _decision({"TLT": 1, "AGG": 1, "SHY": 0}, missing_prices=True)
    )
    assert out.base_weights == {"TLT": 0.0, "AGG": 0.0, "SHY": 1.0}
    assert out.rule_id == "BASE_DATA_FALLBACK_SHY_001"


def test_missing_required_state_raises():
    with pytest.raises(ValueError):
        allocate_base_weights(
            Decision(date="d", regime="dovish_neutral", direction=None,
                     price_state={"missing_prices": False})
        )
