"""Server-side home for the inline numeric reductions Streamlit did in-tab (spec
§2.4.4, §3.1).

These few lines (ETF price stats now; NAV summary later) lived in the Streamlit
layer, not in ``src/``. Per the design rule they move here -- the *one* place the
API is allowed to do arithmetic that isn't already in the engine -- so React
doesn't reimplement them and there is a single source of truth. Everything is a
plain pandas reduction; nothing trading/decision-related lives here.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from api.schemas.backtest import ScenarioSummaryRow
from api.schemas.etf import PriceStat
from api.serialization.frames import nan_to_none


def _clean_float(value: object) -> float | None:
    """Coerce a (possibly numpy) scalar to a finite Python ``float`` or ``None``.

    ``Series.iloc[...]`` / ``Series.min()`` return numpy scalars; orjson does not
    serialize numpy floats by default, so we coerce to native ``float`` here and
    route through :func:`nan_to_none` so NaN/Inf become ``None`` (§6).
    """
    cleaned = nan_to_none(value)
    if isinstance(cleaned, (int, float)):
        return float(cleaned)
    return None


def etf_price_stats(df: pd.DataFrame, tickers: Iterable[str]) -> list[PriceStat]:
    """Per-ticker first/last/min/max close + total return (Tab 4 stats table).

    Reproduces ``etf_prices.py``'s inline stats but as **raw numbers** (the React
    layer formats them, §4.1). Rows are emitted in ``tickers`` order; a ticker
    with no rows is skipped (matching the Streamlit tab). ``df`` has columns
    ``date, close, ticker``; we sort by ``date`` so first/last are chronological
    rather than relying on DB row order.
    """
    stats: list[PriceStat] = []
    for ticker in tickers:
        sub = df[df["ticker"] == ticker].sort_values("date")
        if sub.empty:
            continue
        close = sub["close"]
        first = close.iloc[0]
        last = close.iloc[-1]

        # Total return = last/first - 1; guard a zero/NaN base (-> None, not Inf).
        if pd.isna(first) or pd.isna(last) or float(first) == 0.0:
            total_return: float | None = None
        else:
            total_return = float(last) / float(first) - 1.0

        stats.append(
            PriceStat(
                ticker=str(ticker),
                first_close=_clean_float(first),
                last_close=_clean_float(last),
                min_close=_clean_float(close.min()),
                max_close=_clean_float(close.max()),
                total_return=total_return,
            )
        )
    return stats


def nav_summary_rows(results: pd.DataFrame) -> list[ScenarioSummaryRow]:
    """Per-scenario performance summary (Tab 1 table).

    Reproduces ``nav_comparison.py``'s inline stats as raw numbers (§4.1):
    final/start NAV -> total return, max drawdown from ``nav.cummax()``, and
    annualized volatility ``ret.std() * sqrt(252)``. Rows are emitted in sorted
    ``scenario_id`` order (matching the Streamlit tab); each scenario is sorted by
    date so first/last are chronological.
    """
    rows: list[ScenarioSummaryRow] = []
    has_ret = "ret" in results.columns
    for scenario_id in sorted(results["scenario_id"].unique()):
        sdf = results[results["scenario_id"] == scenario_id].sort_values("date")
        nav = sdf["nav"]
        if nav.empty:
            continue

        final_nav = nav.iloc[-1]
        start_nav = nav.iloc[0]
        if pd.isna(start_nav) or float(start_nav) == 0.0:
            total_return: float | None = None
        else:
            total_return = _clean_float(final_nav / start_nav - 1.0)

        peak = nav.cummax()
        max_drawdown = _clean_float((nav / peak - 1.0).min())
        annualized_volatility = _clean_float(sdf["ret"].std() * (252 ** 0.5)) if has_ret else None

        rows.append(
            ScenarioSummaryRow(
                scenario_id=str(scenario_id),
                final_nav=_clean_float(final_nav),
                total_return=total_return,
                max_drawdown=max_drawdown,
                annualized_volatility=annualized_volatility,
            )
        )
    return rows


def buy_and_hold_nav(prices: pd.DataFrame, initial_nav: float) -> pd.DataFrame:
    """Buy-and-hold NAV line for one benchmark ticker (spec §4.4).

    Replicates ``nav_comparison.py``: buy ``initial_nav / first_close`` shares at
    the window's first close, then NAV(t) = close(t) * shares. ``prices`` has
    columns ``date, close``, already windowed to the backtest start and
    date-sorted. A degenerate first close yields NaN NAV (-> null points at the
    §6 boundary) rather than Inf or a ZeroDivisionError.
    """
    out = prices.copy()
    first_close = out["close"].iloc[0]
    if pd.isna(first_close) or float(first_close) == 0.0:
        out["nav"] = float("nan")
        return out[["date", "nav"]]
    shares = initial_nav / float(first_close)
    out["nav"] = out["close"] * shares
    return out[["date", "nav"]]
