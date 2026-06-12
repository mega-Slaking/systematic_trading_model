"""Volatility-features service (spec endpoints 8 + 9).

Wraps ``db_reader.get_volatility_features`` (the persisted, scenario-independent
surface) into per-ticker vol lines and the latest-per-ticker table.
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

import pandas as pd

from src.storage.db_reader import get_volatility_features

from api.schemas.volatility import VolatilityFeaturesResponse, VolatilityLatestResponse, VolLatestRow
from api.serialization.frames import df_to_series, nan_to_none

# Raw annualized vol estimates in display order (mirrors the tab's _VOL_METHODS).
_VOL_METHODS: dict[str, str] = {
    "rolling_20": "Rolling 20d",
    "rolling_60": "Rolling 60d",
    "ewma_94": "EWMA λ=0.94",
    "ewma_97": "EWMA λ=0.97",
    "garch": "GARCH(1,1)",
}


def _clean_float(value: object) -> float | None:
    cleaned = nan_to_none(value)
    return float(cleaned) if isinstance(cleaned, (int, float)) and not isinstance(cleaned, bool) else None


def get_volatility_for_ticker(ticker: str, methods: list[str] | None = None) -> VolatilityFeaturesResponse:
    """Per-method vol lines for one ticker (endpoint 8)."""
    df = get_volatility_features([ticker])
    if df.empty:
        return VolatilityFeaturesResponse(ticker=ticker, series=[], available_methods=[])

    tdf = df.sort_values("date")
    available = [m for m in _VOL_METHODS if m in tdf.columns and tdf[m].notna().any()]
    requested = [m for m in (methods or available) if m in available]

    series = [
        df_to_series(tdf, name=_VOL_METHODS[m], x="date", y=m, meta={"method": m})
        for m in requested
    ]
    return VolatilityFeaturesResponse(ticker=ticker, series=series, available_methods=available)


def get_volatility_latest() -> VolatilityLatestResponse:
    """Latest annualized vol per method per ticker (endpoint 9)."""
    methods = list(_VOL_METHODS)
    df = get_volatility_features()
    if df.empty:
        return VolatilityLatestResponse(methods=methods, rows=[])

    latest = df.sort_values("date").groupby("ticker").tail(1).sort_values("ticker")
    rows = [
        VolLatestRow(
            ticker=str(row["ticker"]),
            date=str(row["date"].date()) if pd.notna(row["date"]) else None,
            rolling_20=_clean_float(row.get("rolling_20")),
            rolling_60=_clean_float(row.get("rolling_60")),
            ewma_94=_clean_float(row.get("ewma_94")),
            ewma_97=_clean_float(row.get("ewma_97")),
            garch=_clean_float(row.get("garch")),
        )
        for _, row in latest.iterrows()
    ]
    return VolatilityLatestResponse(methods=methods, rows=rows)
