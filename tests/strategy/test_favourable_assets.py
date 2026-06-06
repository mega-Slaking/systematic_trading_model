"""Exhaustive regime -> favourable-asset direction table
(src/decision/favourable_asset_selection.py). Locks the strategy lookup.
"""

import pytest

from src.decision.models import Decision
from src.decision.favourable_asset_selection import determine_favourable_assets

pytestmark = [pytest.mark.unit, pytest.mark.regression]


# (regime, expected direction) for every branch in determine_favourable_assets.
REGIME_DIRECTION_CASES = [
    ("data_fallback", {"TLT": 0, "AGG": 0, "SHY": 1}),
    ("dovish_bearish", {"TLT": 1, "AGG": 1, "SHY": 0}),
    ("dovish_neutral", {"TLT": 1, "AGG": 1, "SHY": 0}),
    ("dovish_bullish", {"TLT": 1, "AGG": 1, "SHY": 0}),
    ("hawkish_bearish", {"TLT": 0, "AGG": 0, "SHY": 1}),
    ("hawkish_neutral", {"TLT": 0, "AGG": 1, "SHY": 1}),
    ("hawkish_bullish", {"TLT": 0, "AGG": 1, "SHY": 1}),
    ("neutral_bearish", {"TLT": 1, "AGG": 1, "SHY": 1}),
    ("neutral_bullish", {"TLT": 0, "AGG": 1, "SHY": 1}),
    # Unknown/mixed regime falls through to the defensive default branch.
    ("some_unhandled_regime", {"TLT": 0, "AGG": 1, "SHY": 1}),
]


@pytest.mark.parametrize("regime,expected", REGIME_DIRECTION_CASES)
def test_regime_maps_to_expected_direction(regime, expected):
    out = determine_favourable_assets(Decision(date="d", regime=regime))
    assert out.direction == expected


def test_missing_regime_raises():
    with pytest.raises(ValueError):
        determine_favourable_assets(Decision(date="d", regime=None))
