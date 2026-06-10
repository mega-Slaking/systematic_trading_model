"""ETF-prices schemas (spec endpoints 6 + 7, Tab 4).

Endpoint 6 (``/etf-prices``) returns one price line per ticker as a
:class:`~api.schemas.common.NamedSeries`; endpoint 7 (``/etf-prices/stats``)
returns the per-ticker price-statistics table that Streamlit computed inline
(``etf_prices.py``) -- moved server-side per spec §2.4.4, and as **raw numbers**
(the React layer formats them, spec §4.1), unlike the Streamlit version which
emitted pre-formatted ``"$..."`` / ``"...%"`` strings.
"""

from __future__ import annotations

from pydantic import BaseModel

from api.schemas.common import NamedSeries


class EtfPricesResponse(BaseModel):
    """Close-price lines, one :class:`NamedSeries` per ticker (Tab 4 chart)."""

    series: list[NamedSeries]


class PriceStat(BaseModel):
    """Per-ticker price statistics (Tab 4 table). Floats are nullable per §6.

    ``total_return`` is a decimal fraction (``last/first - 1``), e.g. ``0.42`` =
    42% -- formatting is the client's job (§4.1).
    """

    ticker: str
    first_close: float | None
    last_close: float | None
    min_close: float | None
    max_close: float | None
    total_return: float | None


class EtfPriceStatsResponse(BaseModel):
    """The price-statistics table as a list of typed rows."""

    stats: list[PriceStat]
