"""Legacy signal-weighted base allocator (src/legacy/legacy_base_weight_allocation.py)."""

import pytest

from src.decision.models import Decision
from src.legacy.legacy_base_weight_allocation import allocate_legacy_base_weights

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def _decision(macro, price=None, regime="neutral_neutral"):
    return Decision(
        date="d",
        regime=regime,
        macro_state=macro,
        price_state=price or {"missing_prices": False, "ret_positive": {}, "momentum": {}},
    )


def test_inflation_rising_is_heavily_defensive():
    out = allocate_legacy_base_weights(_decision({"inflation_rising": True}))
    assert out.legacy_base_weights == {"TLT": 0.0, "AGG": 0.15, "SHY": 0.85}


def test_disinflation_with_confirmation_overweights_tlt():
    macro = {"disinflation": True, "macro_supports_duration": True}
    price = {"missing_prices": False, "ret_positive": {"TLT": True}, "momentum": {}}
    out = allocate_legacy_base_weights(_decision(macro, price))
    assert out.legacy_base_weights == {"TLT": 0.80, "AGG": 0.20, "SHY": 0.00}


def test_data_fallback_to_shy():
    out = allocate_legacy_base_weights(_decision({}, regime="data_fallback"))
    assert out.legacy_base_weights == {"TLT": 0.0, "AGG": 0.0, "SHY": 1.0}


def test_neutral_with_agg_momentum_overweights_agg():
    price = {"missing_prices": False, "ret_positive": {"AGG": True}, "momentum": {}}
    out = allocate_legacy_base_weights(_decision({}, price))
    assert out.legacy_base_weights == {"TLT": 0.10, "AGG": 0.75, "SHY": 0.15}


def test_missing_required_state_raises():
    with pytest.raises(ValueError):
        allocate_legacy_base_weights(Decision(date="d", regime=None))
