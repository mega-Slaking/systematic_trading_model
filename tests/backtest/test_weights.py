"""Unit tests for portfolio weight utilities (src/utils/weights.py)."""

import pytest

from src.utils.weights import (
    normalize_weights,
    clip_weights,
    drift_l1,
    turnover_l1,
)

pytestmark = pytest.mark.unit


class TestNormalizeWeights:
    def test_already_normalized_unchanged(self):
        w = {"TLT": 0.5, "AGG": 0.3, "SHY": 0.2}
        assert normalize_weights(w) == pytest.approx(w)

    def test_rescales_to_sum_one(self):
        out = normalize_weights({"TLT": 2.0, "AGG": 2.0})
        assert out == pytest.approx({"TLT": 0.5, "AGG": 0.5})
        assert sum(out.values()) == pytest.approx(1.0)

    def test_negatives_clipped_to_zero(self):
        out = normalize_weights({"TLT": -1.0, "AGG": 1.0})
        assert out == pytest.approx({"TLT": 0.0, "AGG": 1.0})

    def test_nan_treated_as_zero(self):
        out = normalize_weights({"TLT": float("nan"), "AGG": 1.0})
        assert out == pytest.approx({"TLT": 0.0, "AGG": 1.0})

    def test_non_numeric_treated_as_zero(self):
        out = normalize_weights({"TLT": "abc", "AGG": 1.0})
        assert out == pytest.approx({"TLT": 0.0, "AGG": 1.0})

    def test_all_zero_returns_zeros(self):
        assert normalize_weights({"TLT": 0.0, "AGG": 0.0}) == {"TLT": 0.0, "AGG": 0.0}

    def test_all_negative_returns_zeros(self):
        assert normalize_weights({"TLT": -1.0, "AGG": -2.0}) == {"TLT": 0.0, "AGG": 0.0}

    def test_empty_dict(self):
        assert normalize_weights({}) == {}


class TestClipWeights:
    def test_within_default_bounds_unchanged(self):
        out = clip_weights({"TLT": 0.5, "AGG": 0.2})
        assert out == {"TLT": 0.5, "AGG": 0.2}

    def test_clips_above_default_max(self):
        assert clip_weights({"TLT": 1.5}) == {"TLT": 1.0}

    def test_clips_below_default_min(self):
        assert clip_weights({"TLT": -0.5}) == {"TLT": 0.0}

    def test_custom_min_and_max(self):
        out = clip_weights(
            {"TLT": 0.05, "AGG": 0.9},
            min_w={"TLT": 0.1},
            max_w={"AGG": 0.5},
        )
        assert out == {"TLT": 0.1, "AGG": 0.5}


class TestDriftAndTurnover:
    def test_drift_l1_is_sum_abs_diff(self):
        assert drift_l1({"TLT": 0.5, "AGG": 0.5}, {"TLT": 0.7, "AGG": 0.3}) == pytest.approx(0.4)

    def test_drift_handles_disjoint_keys(self):
        assert drift_l1({"TLT": 1.0}, {"AGG": 1.0}) == pytest.approx(2.0)

    def test_turnover_is_half_drift(self):
        assert turnover_l1({"TLT": 0.5, "AGG": 0.5}, {"TLT": 0.7, "AGG": 0.3}) == pytest.approx(0.2)

    def test_no_change_is_zero_turnover(self):
        w = {"TLT": 0.5, "AGG": 0.5}
        assert turnover_l1(w, w) == 0.0
