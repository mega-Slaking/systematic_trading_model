"""Phase 6 — state-range (shading) + transition (marker) tests."""

import pandas as pd
import pytest

from src.volatility.transitions import (
    build_state_ranges,
    detect_persistent_state_transitions,
)


def _series(states, start="2021-01-01"):
    idx = pd.bdate_range(start, periods=len(states))
    return pd.Series(states, index=idx, dtype=object)


# --------------------------------------------------------------------------- #
# build_state_ranges
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_state_ranges_are_contiguous_and_nonoverlapping():
    s = _series(["Calm", "Calm", "Stress Expansion", "Stress Expansion", "Stress Expansion", "Calm"])
    ranges = build_state_ranges(s)
    assert ranges["state"].tolist() == ["Calm", "Stress Expansion", "Calm"]
    assert ranges.loc[0, "start"] == s.index[0] and ranges.loc[0, "end"] == s.index[1]
    assert ranges.loc[1, "start"] == s.index[2] and ranges.loc[1, "end"] == s.index[4]
    # Non-overlapping: each range starts strictly after the previous one ends.
    assert (ranges["start"].iloc[1:].to_numpy() > ranges["end"].iloc[:-1].to_numpy()).all()


@pytest.mark.unit
def test_state_ranges_empty():
    assert build_state_ranges(pd.Series(dtype=object)).empty


# --------------------------------------------------------------------------- #
# detect_persistent_state_transitions
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_transitions_on_confirmed_change():
    s = _series(["Calm", "Calm", "Stress Expansion", "Stress Expansion", "Normalisation"])
    tr = detect_persistent_state_transitions(s, cooldown_days=1)
    assert tr["kind"].tolist() == ["entered_stress_expansion", "entered_normalisation"]
    assert tr.iloc[0]["from_state"] == "Calm" and tr.iloc[0]["to_state"] == "Stress Expansion"
    assert tr.iloc[0]["label"] == "Entered Stress Expansion"
    assert tr.iloc[0]["date"] == s.index[2]


@pytest.mark.unit
def test_cooldown_suppresses_same_kind_repeats():
    # B at pos2, A at pos4, B at pos6. entered_b repeats at pos6 (gap 4).
    s = _series(["A", "A", "B", "B", "A", "A", "B", "B"])
    # cooldown 10: the second entered_b (gap 4 < 10) is suppressed.
    gated = detect_persistent_state_transitions(s, cooldown_days=10)
    assert gated["kind"].tolist() == ["entered_b", "entered_a"]
    # cooldown 1: every confirmed change is emitted.
    ungated = detect_persistent_state_transitions(s, cooldown_days=1)
    assert ungated["kind"].tolist() == ["entered_b", "entered_a", "entered_b"]


@pytest.mark.unit
def test_no_transitions_for_constant_series():
    assert detect_persistent_state_transitions(_series(["Calm"] * 5)).empty
