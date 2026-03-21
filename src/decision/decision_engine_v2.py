from datetime import datetime
import pandas as pd

from src.decision.constraints import WeightConstraints, apply_constraints

TARGET_TICKERS = ["TLT", "AGG", "SHY"]


def _latest_row(df: pd.DataFrame, ticker: str) -> pd.Series | None:
    rows = df[df["ticker"] == ticker].sort_values("date")
    if rows.empty:
        return None
    return rows.iloc[-1]


def decide_allocation_v2(
    price_signals: pd.DataFrame,
    macro_signals: pd.DataFrame,
    constraints: WeightConstraints | None = None,
) -> dict:
    constraints = constraints or WeightConstraints()

    latest_macro = macro_signals.sort_values("date").iloc[-1]

    latest_tlt = _latest_row(price_signals, "TLT")
    latest_agg = _latest_row(price_signals, "AGG")
    latest_shy = _latest_row(price_signals, "SHY")

    # If any price rows are missing, fall back to SHY 100%
    if any(x is None for x in (latest_tlt, latest_agg, latest_shy)):
        weights = apply_constraints(
            {"TLT": 0.0, "AGG": 0.0, "SHY": 1.0},
            constraints,
        )
        return {
            "date": datetime.utcnow().isoformat(),
            "weights": weights,
            "rule_id": "DATA_FALLBACK_SHY_001",
            "reason": "Missing price signals → fallback to SHY",
            "tlt_ret": float(latest_tlt["ret_lookback"]) if latest_tlt is not None else None,
            "agg_ret": float(latest_agg["ret_lookback"]) if latest_agg is not None else None,
            "shy_ret": float(latest_shy["ret_lookback"]) if latest_shy is not None else None,
            "macro": {
                "cpi_yoy": float(latest_macro["cpi_yoy"]),
            },
        }

    # Macro regimes
    disinflation = (
        bool(latest_macro["cpi_direction_down"]) and
        bool(latest_macro["cpi_accel_down"])
    )
    inflation_rising = not bool(latest_macro["cpi_direction_down"])
    curve_inverted = bool(latest_macro["curve_inverted"])
    growth_slowing = bool(latest_macro["growth_slowing"])
    labor_weakening = bool(latest_macro["labor_weakening"])
    macro_supports_duration = curve_inverted or growth_slowing or labor_weakening

    # Price momentum
    tlt_pos = float(latest_tlt["ret_lookback"]) > 0.0
    agg_pos = float(latest_agg["ret_lookback"]) > 0.0

    # ----------------------------
    # Version 2: produce weights
    # ----------------------------

    raw_weights: dict[str, float]
    rule_id: str
    reason: str

    if inflation_rising:
        # Avoid duration, but you can keep some AGG (optional)
        raw_weights = {"TLT": 0.00, "AGG": 0.15, "SHY": 0.85}
        reason = "Inflation rising → heavily defensive (SHY), small AGG buffer"
        rule_id = "INF_WGT_001"

    elif disinflation:
        if macro_supports_duration and tlt_pos:
            # Strong risk-off / duration regime: overweight TLT but not 100%
            raw_weights = {"TLT": 0.80, "AGG": 0.20, "SHY": 0.00}
            reason = "Strong disinflation + macro confirmation + TLT momentum → overweight TLT"
            rule_id = "DIS_WGT_TLT_001"

        elif agg_pos:
            # Disinflation but weaker confirmation: diversified bonds tilt
            raw_weights = {"TLT": 0.25, "AGG": 0.60, "SHY": 0.15}
            reason = "Disinflation but weak confirmation → tilt AGG, keep some TLT + SHY"
            rule_id = "DIS_WGT_AGG_001"

        else:
            raw_weights = {"TLT": 0.15, "AGG": 0.65, "SHY": 0.20}
            reason = "Disinflation but no positive momentum → defensive AGG tilt"
            rule_id = "DIS_WGT_AGG_002"

    else:
        # Neutral inflation regime
        if agg_pos:
            raw_weights = {"TLT": 0.10, "AGG": 0.75, "SHY": 0.15}
            reason = "Neutral inflation + AGG momentum → overweight AGG"
            rule_id = "NEU_WGT_AGG_001"
        else:
            raw_weights = {"TLT": 0.00, "AGG": 0.25, "SHY": 0.75}
            reason = "Neutral inflation + no positive momentum → defensive mix (mostly SHY)"
            rule_id = "NEU_WGT_SHY_001"

    # Apply constraints (caps/floors/eligibility/shy_floor/etc.) and normalize
    weights = apply_constraints(raw_weights, constraints)

    return {
        "date": datetime.utcnow().isoformat(),
        "weights": weights,
        "rule_id": rule_id,
        "reason": reason,
        "tlt_ret": float(latest_tlt["ret_lookback"]),
        "agg_ret": float(latest_agg["ret_lookback"]),
        "shy_ret": float(latest_shy["ret_lookback"]),
        "macro": {
            "cpi_yoy": float(latest_macro["cpi_yoy"]),
            "disinflation": disinflation,
            "curve_inverted": curve_inverted,
            "growth_slowing": growth_slowing,
            "labor_weakening": labor_weakening,
        },
    }