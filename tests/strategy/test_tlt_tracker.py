"""TLT-tracking allocator state machine (src/strategy/tlt_tracker.py).

Drives the FSM on synthetic price-signal paths (no DB) to lock the behavior the
strategy is built around: a confirmation lag on the way up, hysteresis that does
not whipsaw inside the band, a faster exit on the way down, the AGG/SHY buffer in
the DOWN state, the macro veto, and determinism.
"""

import numpy as np
import pandas as pd
import pytest

from src.decision.models import Decision
from src.strategy.tlt_tracker import (
    TltTrackerConfig,
    allocate_tlt_tracker_weights,
    tlt_tracker_path,
)

pytestmark = [pytest.mark.unit]


def _arr(values):
    return np.asarray(values, dtype=float)


def _signal_frame(slope_z, trend_up, ret_lookback, ticker="TLT", start="2020-01-01"):
    """A price_signals-shaped frame (one row per day) for the given ticker."""
    dates = pd.bdate_range(start, periods=len(slope_z))
    return pd.DataFrame(
        {
            "date": dates,
            "ticker": ticker,
            "ma_slope_z": slope_z,
            "trend_up": trend_up,
            "ret_lookback": ret_lookback,
        }
    )


def _decision(regime="dovish_bullish", macro=None):
    return Decision(
        date="d",
        regime=regime,
        price_state={"missing_prices": False},
        macro_state=macro or {},
    )


def test_no_entry_before_confirmation_lag():
    cfg = TltTrackerConfig()
    n = cfg.min_hold_days + cfg.entry_confirm_days + 5
    path = tlt_tracker_path(_arr([0.6] * n), [True] * n, _arr([0.02] * n), cfg)

    first_up = next((i for i, p in enumerate(path) if p["state"] == "UP"), None)
    assert first_up is not None
    # The lag: cannot enter UP before the minimum dwell time has elapsed.
    assert first_up >= cfg.min_hold_days
    assert all(p["state"] == "NEUTRAL" for p in path[:first_up])


def test_uptrend_ramps_tlt_gradually_toward_max():
    cfg = TltTrackerConfig()
    n = 40
    path = tlt_tracker_path(_arr([0.6] * n), [True] * n, _arr([0.02] * n), cfg)

    assert path[-1]["state"] == "UP"
    assert path[-1]["tlt_w"] == pytest.approx(cfg.tlt_max)

    # The ramp is gradual (first-order lag), not a snap: the first UP step only
    # advances by ramp_step from the neutral start.
    first_up = next(i for i, p in enumerate(path) if p["state"] == "UP")
    assert path[first_up]["tlt_w"] == pytest.approx(cfg.tlt_neutral + cfg.ramp_step)


def test_hysteresis_band_holds_state():
    cfg = TltTrackerConfig()
    up = cfg.min_hold_days + cfg.entry_confirm_days + 5
    band = 10  # slope_z = 0.0 sits inside [slope_exit, slope_enter]
    slope = _arr([0.6] * up + [0.0] * band)
    trend = [True] * (up + band)
    ret = _arr([0.02] * (up + band))
    path = tlt_tracker_path(slope, trend, ret, cfg)

    assert path[up - 1]["state"] == "UP"
    # Drifting into the band must NOT flip the state (anti-whipsaw).
    assert path[-1]["state"] == "UP"


def test_downtrend_exits_faster_than_it_entered():
    cfg = TltTrackerConfig()
    up = cfg.min_hold_days + cfg.entry_confirm_days + 5
    down = 10
    slope = _arr([0.6] * up + [-0.5] * down)
    trend = [True] * up + [False] * down
    ret = _arr([0.02] * up + [-0.02] * down)
    path = tlt_tracker_path(slope, trend, ret, cfg)

    first_down_rel = next(
        i for i, p in enumerate(path[up:]) if p["state"] == "DOWN"
    )
    # Exit confirmation is faster than entry confirmation.
    assert first_down_rel <= cfg.exit_confirm_days
    assert path[-1]["state"] == "DOWN"
    assert path[-1]["tlt_w"] == pytest.approx(cfg.tlt_min)


def test_down_state_buffers_into_agg_and_shy():
    cfg = TltTrackerConfig()
    up = cfg.min_hold_days + cfg.entry_confirm_days + 5
    down = 12
    frame = _signal_frame(
        _arr([0.6] * up + [-0.5] * down),
        [True] * up + [False] * down,
        _arr([0.02] * up + [-0.02] * down),
    )
    out = allocate_tlt_tracker_weights(_decision(), frame, TltTrackerConfig())

    assert out.base_weights["TLT"] < 0.10
    assert out.base_weights["AGG"] >= 0.40   # buffered into AGG
    assert out.base_weights["SHY"] >= 0.40   # and SHY
    assert sum(out.base_weights.values()) == pytest.approx(1.0)
    # The sizer (starting_weight_source="conviction") reads conviction_weights.
    assert out.conviction_weights == out.base_weights


def test_uptrend_allocates_heavy_tlt():
    cfg = TltTrackerConfig()
    frame = _signal_frame(_arr([0.6] * 40), [True] * 40, _arr([0.02] * 40))
    out = allocate_tlt_tracker_weights(_decision(), frame, cfg)

    assert out.base_weights["TLT"] == pytest.approx(cfg.tlt_max)
    assert out.base_weights["SHY"] == pytest.approx(cfg.shy_min)
    assert sum(out.base_weights.values()) == pytest.approx(1.0)


def test_macro_veto_caps_tlt_on_uptrend():
    cfg = TltTrackerConfig()
    frame = _signal_frame(_arr([0.6] * 40), [True] * 40, _arr([0.02] * 40))
    macro = {
        "inflation_rising": True,
        "real_rate_tight": True,
        "growth_slowing": True,
        "monetary_regime": "hawkish",
    }
    out = allocate_tlt_tracker_weights(_decision(macro=macro), frame, cfg)

    assert out.base_weights["TLT"] <= cfg.macro_veto_tlt_cap + 1e-9


def test_macro_confirm_relaxes_the_veto():
    cfg = TltTrackerConfig()
    frame = _signal_frame(_arr([0.6] * 40), [True] * 40, _arr([0.02] * 40))
    macro = {
        "inflation_rising": True,
        "real_rate_tight": True,
        "growth_slowing": True,
        "monetary_regime": "hawkish",
        "macro_supports_duration": True,  # confirmation overrides the veto
    }
    out = allocate_tlt_tracker_weights(_decision(macro=macro), frame, cfg)

    assert out.base_weights["TLT"] == pytest.approx(cfg.tlt_max)


def test_data_fallback_forces_shy():
    frame = pd.DataFrame(
        columns=["date", "ticker", "ma_slope_z", "trend_up", "ret_lookback"]
    )
    decision = Decision(date="d", regime="data_fallback", price_state={"missing_prices": True})
    out = allocate_tlt_tracker_weights(decision, frame, TltTrackerConfig())

    assert out.base_weights == {"TLT": 0.0, "AGG": 0.0, "SHY": 1.0}


def test_warmup_nan_slope_stays_neutral():
    cfg = TltTrackerConfig()
    frame = _signal_frame(
        _arr([np.nan] * 30), [False] * 30, _arr([np.nan] * 30)
    )
    out = allocate_tlt_tracker_weights(_decision(), frame, cfg)

    assert out.base_weights["TLT"] == pytest.approx(cfg.tlt_neutral)
    assert sum(out.base_weights.values()) == pytest.approx(1.0)


def test_path_is_deterministic():
    cfg = TltTrackerConfig()
    args = (_arr([0.5] * 30), [True] * 30, _arr([0.01] * 30), cfg)
    assert tlt_tracker_path(*args) == tlt_tracker_path(*args)
