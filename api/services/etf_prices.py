"""ETF-prices service (spec endpoints 6 + 7).

Wraps the canonical reader ``src/storage/db_reader.py:get_etf_history`` and shapes
its DataFrame into response schemas: close-price lines (one ``NamedSeries`` per
ticker) and the price-statistics table (delegated to ``summaries.py``). No new
analytics -- just a read + the serialization boundary.
"""

from __future__ import annotations

# Side-effect import: ensures the repo root + src/ are on sys.path even if this
# service is imported in isolation (e.g. a unit test) without going through
# api.main. Idempotent (spec §3.3).
from api import _bootstrap  # noqa: F401

from src.storage.db_reader import get_etf_history

from api.schemas.etf import EtfPricesResponse, EtfPriceStatsResponse
from api.serialization.frames import df_to_series
from api.services import summaries

# Canonical display order (matches the Streamlit tab: long-duration -> cash-like).
# Any ticker outside this list is appended alphabetically, so a future ticker
# still renders deterministically.
DEFAULT_TICKER_ORDER = ("TLT", "AGG", "SHY")


def _ordered_tickers(present: list[str], requested: list[str] | None) -> list[str]:
    """Order the tickers to render: requested order if given, else canonical."""
    if requested:
        return [t for t in requested if t in present]
    ranked = [t for t in DEFAULT_TICKER_ORDER if t in present]
    extras = sorted(t for t in present if t not in DEFAULT_TICKER_ORDER)
    return ranked + extras


def get_etf_prices(tickers: list[str] | None = None) -> EtfPricesResponse:
    """Close-price lines for the requested tickers (all three by default)."""
    df = get_etf_history(tickers)
    if df.empty:
        return EtfPricesResponse(series=[])

    present = [str(t) for t in df["ticker"].unique()]
    series = []
    for ticker in _ordered_tickers(present, tickers):
        sub = df[df["ticker"] == ticker].sort_values("date")
        if sub.empty:
            continue
        series.append(df_to_series(sub, name=ticker, x="date", y="close"))
    return EtfPricesResponse(series=series)


def get_etf_price_stats(tickers: list[str] | None = None) -> EtfPriceStatsResponse:
    """Per-ticker price-statistics table (first/last/min/max close + total return)."""
    df = get_etf_history(tickers)
    if df.empty:
        return EtfPriceStatsResponse(stats=[])

    present = [str(t) for t in df["ticker"].unique()]
    ordered = _ordered_tickers(present, tickers)
    return EtfPriceStatsResponse(stats=summaries.etf_price_stats(df, ordered))
