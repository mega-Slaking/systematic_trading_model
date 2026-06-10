"""ETF-prices router (spec endpoints 6 + 7, Tab 4).

Two cheap synchronous DB-read endpoints (§5.1): the close-price lines and the
price-statistics table. ``tickers`` is an optional comma-separated filter
(``?tickers=TLT,AGG,SHY``); omitted means all.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas.etf import EtfPricesResponse, EtfPriceStatsResponse
from api.services import etf_prices as service

router = APIRouter(prefix="/etf-prices", tags=["etf-prices"])

_TICKERS_QUERY = Query(
    default=None,
    description="Comma-separated tickers (e.g. TLT,AGG,SHY). Omit for all.",
    examples=["TLT,AGG,SHY"],
)


def _parse_tickers(tickers: str | None) -> list[str] | None:
    """Split/normalize the comma-separated ``tickers`` query param to a list or None."""
    if not tickers:
        return None
    parsed = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    return parsed or None


@router.get("", response_model=EtfPricesResponse, summary="ETF close-price lines")
def etf_prices(tickers: str | None = _TICKERS_QUERY) -> EtfPricesResponse:
    """One close-price :class:`NamedSeries` per ticker (Tab 4 chart)."""
    return service.get_etf_prices(_parse_tickers(tickers))


@router.get("/stats", response_model=EtfPriceStatsResponse, summary="ETF price statistics")
def etf_price_stats(tickers: str | None = _TICKERS_QUERY) -> EtfPriceStatsResponse:
    """Per-ticker first/last/min/max close + total return (Tab 4 table)."""
    return service.get_etf_price_stats(_parse_tickers(tickers))
