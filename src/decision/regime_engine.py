from datetime import datetime
import pandas as pd

from src.decision.models import Decision

TARGET_TICKERS = ["TLT", "AGG", "SHY"]


def _latest_row(df: pd.DataFrame, ticker: str) -> pd.Series | None:
    rows = df[df["ticker"] == ticker].sort_values("date")
    if rows.empty:
        return None
    return rows.iloc[-1]


def evaluate_regime(
    decision: Decision,
    price_signals: pd.DataFrame,
    macro_signals: pd.DataFrame,
) -> Decision: #return mutated object - pass through each stage of decision making
    latest_macro = macro_signals.sort_values("date").iloc[-1]

    latest_tlt = _latest_row(price_signals, "TLT")
    latest_agg = _latest_row(price_signals, "AGG")
    latest_shy = _latest_row(price_signals, "SHY")

    missing_prices = any(x is None for x in (latest_tlt, latest_agg, latest_shy))

    if missing_prices:
        decision.rule_id = "DATA_FALLBACK_001"
        decision.reason = "Missing price signals"
        decision.regime = "data_fallback"

        decision.price_state = {
            "missing_prices": True,
            "returns": {
                "TLT": float(latest_tlt["ret_lookback"]) if latest_tlt is not None else None,
                "AGG": float(latest_agg["ret_lookback"]) if latest_agg is not None else None,
                "SHY": float(latest_shy["ret_lookback"]) if latest_shy is not None else None,
            },
            "momentum": None,
        }

        decision.macro_state = {
            "cpi_yoy": float(latest_macro["cpi_yoy"]),
        }

        decision.direction = {
            "TLT": 0,
            "AGG": 0,
            "SHY": 1,
        }

        decision.notes.append("Fallback regime triggered due to missing price signals.")
        return decision

    disinflation = (
        bool(latest_macro["cpi_direction_down"])
        and bool(latest_macro["cpi_accel_down"])
    )
    inflation_rising = not bool(latest_macro["cpi_direction_down"])
    curve_inverted = bool(latest_macro["curve_inverted"])
    growth_slowing = bool(latest_macro["growth_slowing"])
    labor_weakening = bool(latest_macro["labor_weakening"])
    macro_supports_duration = curve_inverted or growth_slowing or labor_weakening

    tlt_pos = float(latest_tlt["ret_lookback"]) > 0.0
    agg_pos = float(latest_agg["ret_lookback"]) > 0.0
    shy_pos = float(latest_shy["ret_lookback"]) > 0.0

    if inflation_rising:
        decision.regime = "inflation_rising"
        decision.rule_id = "REGIME_INF_001"
        decision.reason = "Inflation direction is rising"
        decision.direction = {
            "TLT": 0,
            "AGG": 1,
            "SHY": 1,
        }

    elif disinflation:
        decision.regime = "disinflation"
        decision.rule_id = "REGIME_DIS_001"
        decision.reason = "Inflation direction and acceleration are both down"
        decision.direction = {
            "TLT": 1,
            "AGG": 1,
            "SHY": 0,
        }

    else:
        decision.regime = "neutral"
        decision.rule_id = "REGIME_NEU_001"
        decision.reason = "Neither rising inflation nor confirmed disinflation"
        decision.direction = {
            "TLT": 0,
            "AGG": 1,
            "SHY": 1,
        }

    decision.price_state = {
        "missing_prices": False,
        "returns": {
            "TLT": float(latest_tlt["ret_lookback"]),
            "AGG": float(latest_agg["ret_lookback"]),
            "SHY": float(latest_shy["ret_lookback"]),
        },
        "momentum": {
            "TLT": tlt_pos,
            "AGG": agg_pos,
            "SHY": shy_pos,
        },
    }

    decision.macro_state = {
        "cpi_yoy": float(latest_macro["cpi_yoy"]),
        "disinflation": disinflation,
        "inflation_rising": inflation_rising,
        "curve_inverted": curve_inverted,
        "growth_slowing": growth_slowing,
        "labor_weakening": labor_weakening,
        "macro_supports_duration": macro_supports_duration,
    }

    return decision