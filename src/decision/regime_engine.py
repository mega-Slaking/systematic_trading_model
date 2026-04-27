import pandas as pd

from src.decision.models import Decision

TARGET_TICKERS = ["TLT", "AGG", "SHY"]


def _latest_row(df: pd.DataFrame, ticker: str) -> pd.Series | None:
    rows = df[df["ticker"] == ticker].sort_values("date")
    if rows.empty:
        return None
    return rows.iloc[-1]

def _safe_optional_float(value):
    if value is None or pd.isna(value):
        return None

    return float(value)


def _classify_monetary_regime(row: pd.Series) -> str:
    disinflation = bool(row.get("disinflation", False))
    inflation_rising = bool(row.get("inflation_rising", False))
    real_rate_tight = bool(row.get("real_rate_tight", False))
    fed_funds_direction = row.get("fed_funds_direction", 0)

    if disinflation and not real_rate_tight:
        return "dovish"

    if inflation_rising and real_rate_tight:
        return "hawkish"

    if fed_funds_direction < 0 and disinflation:
        return "dovish"

    if fed_funds_direction > 0 and inflation_rising:
        return "hawkish"

    return "neutral"


def _classify_economic_regime(row: pd.Series) -> str:
    bearish_count = sum([
        bool(row.get("growth_slowing", False)),
        bool(row.get("labor_weakening", False)),
        bool(row.get("jobless_rising", False)),
        bool(row.get("credit_spread_widening", False)),
        bool(row.get("confidence_low", False)),
    ])

    if bearish_count >= 3:
        return "bearish"

    if bearish_count == 0:
        return "bullish"

    return "neutral"


def evaluate_regime(
    decision: Decision,
    price_signals: pd.DataFrame,
    macro_signals: pd.DataFrame,
) -> Decision:
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
                "TLT": _safe_optional_float(latest_tlt.get("ret_lookback")) if latest_tlt is not None else None,
                "AGG": _safe_optional_float(latest_agg.get("ret_lookback")) if latest_agg is not None else None,
                "SHY": _safe_optional_float(latest_shy.get("ret_lookback")) if latest_shy is not None else None,
            },
            "ret_positive": {
                "TLT": False,
                "AGG": False,
                "SHY": False,
            },
            "momentum": {
                "TLT": False,
                "AGG": False,
                "SHY": False,
            },
            "ma_slope_z": {
                "TLT": None,
                "AGG": None,
                "SHY": None,
            },
        }

        decision.macro_state = {
            "cpi_yoy": float(latest_macro.get("cpi_yoy")),
        }

        decision.direction = {
            "TLT": 0,
            "AGG": 0,
            "SHY": 1,
        }

        decision.notes.append("Fallback regime triggered due to missing price signals.")
        return decision

    monetary_regime = _classify_monetary_regime(latest_macro)
    economic_regime = _classify_economic_regime(latest_macro)
    regime = f"{monetary_regime}_{economic_regime}"

    # tlt_pos = float(latest_tlt["ret_lookback"]) > 0.0
    # agg_pos = float(latest_agg["ret_lookback"]) > 0.0
    # shy_pos = float(latest_shy["ret_lookback"]) > 0.0

    decision.regime = regime
    decision.monetary_regime = monetary_regime
    decision.economic_regime = economic_regime
    decision.rule_id = f"REGIME_{regime.upper()}_001"
    decision.reason = f"Monetary regime is {monetary_regime}; economic regime is {economic_regime}"

    tlt_ret = _safe_optional_float(latest_tlt.get("ret_lookback"))
    agg_ret = _safe_optional_float(latest_agg.get("ret_lookback"))
    shy_ret = _safe_optional_float(latest_shy.get("ret_lookback"))

    decision.price_state = {
        "missing_prices": False,
        "returns": {
            "TLT": tlt_ret,
            "AGG": agg_ret,
            "SHY": shy_ret,
        },
        "ret_positive": {
            "TLT": (tlt_ret or 0.0) > 0.0,
            "AGG": (agg_ret or 0.0) > 0.0,
            "SHY": (shy_ret or 0.0) > 0.0,
        },
        "momentum": {
            "TLT": bool(latest_tlt.get("trend_up", False)),
            "AGG": bool(latest_agg.get("trend_up", False)),
            "SHY": bool(latest_shy.get("trend_up", False)),
        },
        "ma_slope_z": {
            "TLT": _safe_optional_float(latest_tlt.get("ma_slope_z")),
            "AGG": _safe_optional_float(latest_agg.get("ma_slope_z")),
            "SHY": _safe_optional_float(latest_shy.get("ma_slope_z")),
        },
    }

    decision.macro_state = {
        "cpi_yoy": float(latest_macro.get("cpi_yoy")),
        "core_cpi_yoy": float(latest_macro.get("core_cpi_yoy")),
        "disinflation": bool(latest_macro.get("disinflation", False)),
        "inflation_rising": bool(latest_macro.get("inflation_rising", False)),
        "growth_slowing": bool(latest_macro.get("growth_slowing", False)),
        "labor_weakening": bool(latest_macro.get("labor_weakening", False)),
        "jobless_rising": bool(latest_macro.get("jobless_rising", False)),
        "curve_inverted": bool(latest_macro.get("curve_inverted", False)),
        "real_rate_tight": bool(latest_macro.get("real_rate_tight", False)),
        "credit_spread_widening": bool(latest_macro.get("credit_spread_widening", False)),
        "confidence_low": bool(latest_macro.get("confidence_low", False)),
        "macro_supports_duration": bool(latest_macro.get("macro_supports_duration", False)),
        "monetary_regime": monetary_regime,
        "economic_regime": economic_regime,
    }

    decision.notes.append(f"Regime evaluated as {regime}.")

    return decision