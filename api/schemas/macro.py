"""Macro schemas (spec endpoints 10 + 11, Page 6).

Endpoint 10 returns one series per requested macro indicator (each on its own
date axis -- macro is monthly and sparse, so series are NaN-dropped, §2.6).
Endpoint 11 returns the 10Y/2Y yields + their spread for the yield-curve chart.
"""

from __future__ import annotations

from pydantic import BaseModel

from api.schemas.common import NamedSeries


class MacroResponse(BaseModel):
    """One :class:`NamedSeries` per requested indicator (name = indicator key)."""

    series: list[NamedSeries]


class YieldCurveResponse(BaseModel):
    """10Y/2Y yields and the 10Y-2Y spread (spread carries meta={'fill':'tozeroy'})."""

    gs10: NamedSeries
    gs2: NamedSeries
    spread: NamedSeries
