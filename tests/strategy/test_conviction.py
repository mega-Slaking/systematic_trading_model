"""Conviction scaling (src/conviction/engine.py): macro/price/direction scoring
tilts base weights, multipliers stay bounded, required inputs validated.
"""

import pytest

from src.decision.models import Decision
from src.conviction.engine import apply_conviction_scaling
from src.conviction.models import ConvictionConfig

pytestmark = pytest.mark.unit


def _decision(base, macro, price=None, direction=None):
    return Decision(
        date="d",
        base_weights=base,
        macro_state=macro,
        price_state=price or {"momentum": {}, "returns": {}, "ma_slope_z": {}},
        direction=direction or {"TLT": 0, "AGG": 0, "SHY": 0},
    )


def test_hostile_macro_tilts_conviction_toward_shy():
    base = {"TLT": 0.5, "AGG": 0.3, "SHY": 0.2}
    macro = {"inflation_rising": True, "real_rate_tight": True, "growth_slowing": True}

    out = apply_conviction_scaling(_decision(base, macro))

    assert sum(out.conviction_weights.values()) == pytest.approx(1.0)
    assert out.conviction_weights["SHY"] > 0.2  # share rose vs base
    assert out.conviction_weights["TLT"] < 0.5  # share fell vs base


def test_supportive_macro_tilts_toward_duration():
    base = {"TLT": 0.34, "AGG": 0.33, "SHY": 0.33}
    macro = {
        "disinflation": True,
        "growth_slowing": True,
        "macro_supports_duration": True,
        "curve_inverted": True,
    }
    out = apply_conviction_scaling(
        _decision(base, macro, direction={"TLT": 1, "AGG": 1, "SHY": 0})
    )
    assert out.conviction_weights["TLT"] > out.conviction_weights["SHY"]


def test_multipliers_within_config_bounds():
    cfg = ConvictionConfig()
    out = apply_conviction_scaling(
        _decision({"TLT": 0.34, "AGG": 0.33, "SHY": 0.33}, {"inflation_rising": True})
    )
    for multiplier in out.conviction.values():
        assert cfg.min_multiplier <= multiplier <= cfg.max_multiplier


@pytest.mark.parametrize("missing", ["base_weights", "macro_state", "price_state", "direction"])
def test_missing_required_field_raises(missing):
    kwargs = dict(
        base_weights={"TLT": 1.0}, macro_state={}, price_state={}, direction={"TLT": 1}
    )
    kwargs[missing] = None
    with pytest.raises(ValueError):
        apply_conviction_scaling(Decision(date="d", **kwargs))
