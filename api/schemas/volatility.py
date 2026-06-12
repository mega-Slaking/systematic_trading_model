"""Volatility-features schemas (spec endpoints 8 + 9, Tab 5).

Endpoint 8 returns the per-method volatility lines for one ticker; endpoint 9 the
latest-per-ticker values table. Methods mirror the tab's ``_VOL_METHODS`` keys.
"""

from __future__ import annotations

from pydantic import BaseModel

from api.schemas.common import NamedSeries


class VolatilityFeaturesResponse(BaseModel):
    """Vol estimate lines for one ticker (Tab 5 chart). Series names are display
    labels; ``meta.method`` carries the raw key. ``available_methods`` lists the
    method keys that are non-empty for this ticker."""

    ticker: str
    series: list[NamedSeries]
    available_methods: list[str]


class VolLatestRow(BaseModel):
    """Latest annualized vol per method for one ticker (Tab 5 table)."""

    ticker: str
    date: str | None
    rolling_20: float | None
    rolling_60: float | None
    ewma_94: float | None
    ewma_97: float | None
    garch: float | None


class VolatilityLatestResponse(BaseModel):
    """Latest-values table across all tickers."""

    methods: list[str]
    rows: list[VolLatestRow]
