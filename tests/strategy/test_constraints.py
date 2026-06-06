"""Final weight constraints (src/decision/constraints.py)."""

import pytest

from src.decision.constraints import apply_constraints, WeightConstraints

pytestmark = pytest.mark.unit


def test_normalizes_to_sum_one():
    out = apply_constraints({"TLT": 2.0, "AGG": 2.0}, WeightConstraints())
    assert out == pytest.approx({"TLT": 0.5, "AGG": 0.5})


def test_eligibility_zeros_then_renormalizes():
    out = apply_constraints({"TLT": 0.5, "AGG": 0.5}, WeightConstraints(eligible=["TLT"]))
    assert out["AGG"] == pytest.approx(0.0)
    assert out["TLT"] == pytest.approx(1.0)


def test_shy_floor_lifts_shy_off_zero():
    # Floor is applied before normalization, so the realized SHY is floor/total.
    out = apply_constraints(
        {"TLT": 1.0, "AGG": 0.0, "SHY": 0.0}, WeightConstraints(shy_floor=0.2)
    )
    assert out["SHY"] > 0.0
    assert out["SHY"] == pytest.approx(0.2 / 1.2)
    assert sum(out.values()) == pytest.approx(1.0)


def test_all_zero_falls_back_to_fallback_ticker():
    out = apply_constraints(
        {"TLT": 0.0, "AGG": 0.0, "SHY": 0.0}, WeightConstraints(fallback_ticker="SHY")
    )
    assert out["SHY"] == pytest.approx(1.0)


def test_max_weight_clip_limits_relative_share():
    out = apply_constraints(
        {"TLT": 1.0, "AGG": 1.0}, WeightConstraints(max_w={"TLT": 0.5})
    )
    assert out["TLT"] == pytest.approx(0.5 / 1.5)
    assert out["AGG"] == pytest.approx(1.0 / 1.5)
