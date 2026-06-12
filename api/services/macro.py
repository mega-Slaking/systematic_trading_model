"""Macro service (spec endpoints 10 + 11).

Wraps ``db_reader.get_macro_history``. Each indicator series is NaN-dropped onto
its own date axis (macro is monthly/sparse, §2.6); the yield-curve endpoint
computes the 10Y-2Y spread the page currently derives inline.
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

from src.storage.db_reader import get_macro_history

from api.schemas.macro import MacroResponse, YieldCurveResponse
from api.serialization.frames import df_to_series

# Indicators exposed by get_macro_history (the FE picks a subset per chart).
_MACRO_INDICATORS: tuple[str, ...] = (
    "cpi",
    "core_cpi",
    "pmi",
    "gs2",
    "gs10",
    "unemployment",
    "payrolls",
    "fed_funds",
    "consumer_sentiment",
    "hy_oas",
    "jobless_claims",
)


def get_macro(indicators: list[str] | None = None) -> MacroResponse:
    """One series per requested indicator (all by default), each NaN-dropped."""
    df = get_macro_history().sort_values("date")
    wanted = [i for i in (indicators or _MACRO_INDICATORS) if i in df.columns]

    series = []
    for indicator in wanted:
        sub = df[["date", indicator]].dropna(subset=[indicator])
        if sub.empty:
            continue
        series.append(df_to_series(sub, name=indicator, x="date", y=indicator))
    return MacroResponse(series=series)


def get_yield_curve() -> YieldCurveResponse:
    """10Y/2Y yields + the 10Y-2Y spread (Page 6 yield-curve chart)."""
    df = get_macro_history().sort_values("date")
    yields = df.dropna(subset=["gs10", "gs2"]).copy()
    yields["spread"] = yields["gs10"] - yields["gs2"]

    return YieldCurveResponse(
        gs10=df_to_series(yields, name="10Y Yield", x="date", y="gs10"),
        gs2=df_to_series(yields, name="2Y Yield", x="date", y="gs2"),
        spread=df_to_series(yields, name="10Y-2Y Spread", x="date", y="spread", meta={"fill": "tozeroy"}),
    )
