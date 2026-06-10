"""TLT-tracking base strategy (the new default allocator).

Thesis (see docs/modular_strategy_and_tlt_tracker_spec.md §4): follow TLT on the
way up *with a lag*, and buffer into AGG/SHY on the way down. TLT is the convex,
high-"temperature" duration bet; when the long end is in a confirmed uptrend we
ramp into it, and when it rolls over we step down the duration ladder into AGG
(intermediate) and SHY (front end) to cut the left tail.

This replaces the old regime-table modern path (favourable_asset_selection ->
base_allocator_engine -> conviction). Those modules were moved to ``src/legacy/``
and their pipeline calls were commented out in ``src/decision/pipeline.py`` (per
the project's comment-out-don't-delete convention). This allocator writes BOTH
``decision.base_weights`` and ``decision.conviction_weights`` so the existing
position sizer (``starting_weight_source="conviction"``) consumes the tracker's
directional weights unchanged.

Look-ahead safety: the state machine is *replayed* over the look-ahead-safe TLT
signal history (``price_signals`` only contains rows dated ``< current_date`` in
the backtest -- see ``src/context/backtest.py``). No mutable cross-day state is
carried, so the result is deterministic and reconstructable from point-in-time
data alone (spec §6/§7). Trend detection reuses the engine's precomputed
``ma_slope_z`` / ``trend_up`` / ``ret_lookback`` columns
(``src/signals_price/price_signal_engine.py``), so the fast/slow MA windows are
inherited from ``config.LOOKBACK_DAYS`` rather than re-parameterised here.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.decision.models import Decision


@dataclass(frozen=True)
class TltTrackerConfig:
    """Sweepable parameters for the TLT tracker (spec §4.7).

    NOTE: ``trend_fast`` / ``trend_slow`` from the spec are intentionally omitted:
    trend detection reuses the engine's precomputed ``ma_slope_z`` (windows set by
    ``config.LOOKBACK_DAYS``). Re-deriving configurable MA windows from raw close
    is deferred to the modular-allocator phase.
    """

    # --- Schmitt-trigger thresholds on TLT's ma_slope_z (anti-whipsaw band) ---
    slope_enter: float = 0.25      # enter UP when slope_z rises above this
    slope_exit: float = -0.10      # exit to DOWN when slope_z falls below this
    # between slope_exit and slope_enter -> hold the previous state (hysteresis)

    # --- confirmation lag (asymmetric: slower in, faster out) ---
    entry_confirm_days: int = 5    # consecutive UP days required before entering UP
    exit_confirm_days: int = 2     # consecutive DOWN days required before exiting
    min_hold_days: int = 5         # minimum dwell time before any state change

    # --- weight ramp (first-order lag toward the state target) ---
    ramp_step: float = 0.20        # max TLT increase per rebalance (slow build)
    ramp_step_down: float = 0.40   # max TLT decrease per rebalance (fast de-risk)

    # --- state -> TLT target levels ---
    tlt_max: float = 0.80          # TLT ceiling on a confirmed uptrend
    tlt_neutral: float = 0.40      # TLT target inside the hysteresis band
    tlt_min: float = 0.00          # TLT floor on a confirmed downtrend

    # --- defensive sleeve shape ---
    agg_defensive: float = 0.50    # AGG weight in the DOWN state
    shy_min: float = 0.05          # SHY floor in UP / NEUTRAL

    # --- macro confirmation / veto (reuses Part A signals; spec §4.6) ---
    macro_veto: bool = True            # cap TLT in hostile rate regimes
    macro_confirm: bool = True         # let macro_supports_duration relax the veto
    macro_veto_tlt_cap: float = 0.40   # TLT cap applied when the veto fires


# State labels used throughout.
_UP, _DOWN, _NEUTRAL, _FALLBACK = "UP", "DOWN", "NEUTRAL", "DATA_FALLBACK"


def tlt_tracker_path(slope_z, trend_up, ret_lookback, cfg: TltTrackerConfig) -> list[dict]:
    """Replay the state machine over the TLT signal history.

    Pure and deterministic: returns one ``{"state", "tlt_w"}`` dict per input day.
    Exposed (not underscore-private) so the FSM can be unit-tested directly on
    synthetic price paths without a DB (spec §6).
    """
    state = _NEUTRAL
    days_in_state = 0
    up_streak = 0
    down_streak = 0
    tlt_w = cfg.tlt_neutral

    path: list[dict] = []
    n = len(slope_z)
    for i in range(n):
        sz = slope_z[i]
        valid = sz == sz  # False iff NaN
        tu = bool(trend_up[i]) if i < len(trend_up) else False
        rl = ret_lookback[i] if i < len(ret_lookback) else float("nan")
        ret_pos = (rl == rl) and (rl > 0.0)

        if valid:
            up_cond = tu and (sz > cfg.slope_enter) and ret_pos
            down_cond = sz < cfg.slope_exit
        else:
            up_cond = False
            down_cond = False

        # Confirmation counters: a streak only accumulates while its condition
        # holds; the hysteresis band (neither condition) resets both.
        if up_cond:
            up_streak += 1
            down_streak = 0
        elif down_cond:
            down_streak += 1
            up_streak = 0
        else:
            up_streak = 0
            down_streak = 0

        # min_hold_days floor: no state change until the current state has been
        # held long enough, regardless of the signal.
        can_change = days_in_state >= cfg.min_hold_days
        new_state = state
        if can_change:
            if state != _UP and up_streak >= cfg.entry_confirm_days:
                new_state = _UP
            elif state != _DOWN and down_streak >= cfg.exit_confirm_days:
                new_state = _DOWN

        if new_state != state:
            state = new_state
            days_in_state = 0
        else:
            days_in_state += 1

        # Ramp TLT toward the state's target (first-order lag); increases are
        # slow (ramp_step), decreases are fast (ramp_step_down) -- the asymmetry
        # protects the left tail.
        if state == _UP:
            target = cfg.tlt_max
        elif state == _DOWN:
            target = cfg.tlt_min
        else:
            target = cfg.tlt_neutral

        if target > tlt_w:
            tlt_w = min(target, tlt_w + cfg.ramp_step)
        elif target < tlt_w:
            tlt_w = max(target, tlt_w - cfg.ramp_step_down)

        path.append({"state": state, "tlt_w": tlt_w})

    return path


def _state_weights(state: str, tlt_w: float, cfg: TltTrackerConfig) -> dict[str, float]:
    """Map (state, TLT weight) -> a long-only, fully-invested {TLT, AGG, SHY}."""
    tlt = max(0.0, min(float(tlt_w), 1.0))

    if state == _DOWN:
        # Buffer the drawdown: cap AGG at agg_defensive, remainder to SHY.
        agg = min(cfg.agg_defensive, 1.0 - tlt)
        shy = 1.0 - tlt - agg
    else:
        # UP / NEUTRAL: keep a small SHY floor, remainder to AGG.
        tlt = min(tlt, 1.0 - cfg.shy_min)
        shy = cfg.shy_min
        agg = 1.0 - tlt - shy

    weights = {"TLT": tlt, "AGG": max(0.0, agg), "SHY": max(0.0, shy)}
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    return weights


def _macro_caps_tlt(macro: dict, cfg: TltTrackerConfig) -> bool:
    """True if the macro/monetary regime is hostile enough to cap TLT.

    Mirrors the stagflation/hawkish veto from the conviction layer
    (``src/conviction/engine.py`` ``_stagflation_pressure``; spec §2.3, §4.6).
    """
    if not cfg.macro_veto:
        return False

    inflation_rising = bool(macro.get("inflation_rising"))
    real_rate_tight = bool(macro.get("real_rate_tight"))
    growth_slowing = bool(macro.get("growth_slowing"))
    labor_weakening = bool(macro.get("labor_weakening"))
    monetary_regime = macro.get("monetary_regime")

    stagflation = inflation_rising and real_rate_tight and (growth_slowing or labor_weakening)
    hawkish_inflation = (monetary_regime == "hawkish") and inflation_rising

    if not (stagflation or hawkish_inflation):
        return False

    # macro_supports_duration is a confirmation that can relax the veto.
    if cfg.macro_confirm and bool(macro.get("macro_supports_duration")):
        return False

    return True


def _direction_for_state(state: str) -> dict[str, int]:
    """Light directional prior for tracing only (not consumed downstream)."""
    if state == _UP:
        return {"TLT": 1, "AGG": 1, "SHY": 0}
    if state == _DOWN:
        return {"TLT": 0, "AGG": 1, "SHY": 1}
    if state == _FALLBACK:
        return {"TLT": 0, "AGG": 0, "SHY": 1}
    return {"TLT": 1, "AGG": 1, "SHY": 1}  # NEUTRAL


def _write_decision(decision: Decision, weights: dict[str, float], *, state: str, reason: str) -> None:
    decision.base_weights = dict(weights)
    # Set conviction_weights too so the sizer (starting_weight_source="conviction")
    # starts from the tracker's directional weights without any sizer changes.
    decision.conviction_weights = dict(weights)
    decision.direction = _direction_for_state(state)
    decision.rule_id = f"TLT_TRACKER_{state}_001"
    decision.reason = reason
    decision.notes.append(
        "TLT tracker: state=%s, weights={'TLT': %.3f, 'AGG': %.3f, 'SHY': %.3f}."
        % (state, weights["TLT"], weights["AGG"], weights["SHY"])
    )


def allocate_tlt_tracker_weights(
    decision: Decision,
    price_signals: pd.DataFrame,
    config: TltTrackerConfig | None = None,
) -> Decision:
    """Set ``decision.base_weights`` from the TLT-tracking state machine.

    Contract (spec §3.2): reads ``decision.regime`` / ``price_state`` /
    ``macro_state`` and the look-ahead-safe ``price_signals`` history; writes
    ``base_weights`` and ``conviction_weights``. Must not use data dated
    ``>= decision.date`` -- guaranteed because ``price_signals`` is the
    point-in-time slice.
    """
    cfg = config or TltTrackerConfig()
    price = decision.price_state or {}

    # Reuse the existing hard defensive gate.
    if decision.regime == "data_fallback" or bool(price.get("missing_prices", False)):
        _write_decision(
            decision,
            {"TLT": 0.0, "AGG": 0.0, "SHY": 1.0},
            state=_FALLBACK,
            reason="Missing price signals -> fallback to SHY",
        )
        return decision

    tlt = price_signals[price_signals["ticker"] == "TLT"].sort_values("date")

    if tlt.empty or "ma_slope_z" not in tlt.columns:
        # Not enough history to form a view -> neutral default.
        state, tlt_w = _NEUTRAL, cfg.tlt_neutral
    else:
        slope_z = pd.to_numeric(tlt["ma_slope_z"], errors="coerce").to_numpy()
        trend_up = (
            tlt["trend_up"].to_numpy()
            if "trend_up" in tlt.columns
            else np.zeros(len(tlt), dtype=bool)
        )
        ret_lookback = (
            pd.to_numeric(tlt["ret_lookback"], errors="coerce").to_numpy()
            if "ret_lookback" in tlt.columns
            else np.full(len(tlt), np.nan)
        )
        path = tlt_tracker_path(slope_z, trend_up, ret_lookback, cfg)
        last = path[-1] if path else {"state": _NEUTRAL, "tlt_w": cfg.tlt_neutral}
        state, tlt_w = last["state"], last["tlt_w"]

    # Macro veto: don't chase duration into a hostile rate phase. Applied as a
    # cap on today's output (the historical ramp uses the price-only target).
    macro = decision.macro_state or {}
    if _macro_caps_tlt(macro, cfg):
        tlt_w = min(tlt_w, cfg.macro_veto_tlt_cap)

    weights = _state_weights(state, tlt_w, cfg)
    _write_decision(
        decision,
        weights,
        state=state,
        reason=f"TLT tracker state={state} (TLT target {weights['TLT']:.2f})",
    )
    return decision
