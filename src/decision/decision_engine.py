from datetime import datetime
import pandas as pd

TARGET_TICKERS = ["TLT", "AGG", "SHY"]

def _latest_row(df: pd.DataFrame, ticker: str) -> pd.Series:
    rows = df[df["ticker"] == ticker].sort_values("date")

    if rows.empty:
        return None

    return rows.iloc[-1]


def decide_allocation(price_signals: pd.DataFrame,
                      macro_signals: pd.DataFrame) -> dict:

    latest_macro = macro_signals.sort_values("date").iloc[-1]

    latest_tlt = _latest_row(price_signals, "TLT")
    latest_agg = _latest_row(price_signals, "AGG")
    latest_shy = _latest_row(price_signals, "SHY")

    #if any(x is None for x in (latest_tlt, latest_agg, latest_shy)):
    #    return None

    #Macro regimes
    disinflation = (
        latest_macro["cpi_direction_down"] and
        latest_macro["cpi_accel_down"]
    )
    inflation_rising = not latest_macro["cpi_direction_down"]
    curve_inverted = latest_macro["curve_inverted"]
    growth_slowing = latest_macro["growth_slowing"]
    labor_weakening = latest_macro["labor_weakening"]
    macro_supports_duration = (
        curve_inverted or
        growth_slowing or
        labor_weakening
    )

    #Price momentum
    tlt_pos = latest_tlt["ret_lookback"] > 0
    agg_pos = latest_agg["ret_lookback"] > 0

    #The actual engine

    if inflation_rising:
        chosen = "SHY"
        reason = "Inflation rising → avoid duration"
        rule_id = "INF_SHY_001"

    elif disinflation:
        if macro_supports_duration and tlt_pos:
            chosen = "TLT"
            reason = "Strong disinflation + macro confirmation + TLT momentum"
            rule_id = "DIS_INV_TLT_001"
        elif agg_pos:
            chosen = "AGG"
            reason = "Disinflation but weak confirmation → AGG"
            rule_id = "DIS_INV_AGG_001"
        else:
            chosen = "AGG"
            reason = "Disinflation but no positive momentum"
            rule_id = "DIS_INV_AGG_002"


    else:
        # Neutral inflation regime
        if agg_pos:
            chosen = "AGG" 
            reason = "Neutral inflation + AGG momentum"
            rule_id = "NEU_AGG_001"
        else:
            chosen = "SHY"
            reason = "Neutral inflation + no positive momentum"
            rule_id = "NEU_SHY_001"

    return {
        "date": datetime.utcnow().isoformat(),
        "chosen": chosen,
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
        }
    }
