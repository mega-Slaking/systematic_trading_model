"""Backtest-results service (spec endpoints 2 + 3).

Wraps the canonical reader ``db_reader.get_backtest_results`` (explicit columns,
**not** ``SELECT *`` -- §2.5/§6) plus ``get_etf_history`` for the benchmarks, and
shapes them into the NAV-comparison and returns-scatter responses. All numeric
reductions (summary stats, B&H scaling) live in ``summaries.py``; this module
only reads, filters, and serializes.
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

import pandas as pd

from src.storage.db_reader import get_backtest_results, get_etf_history

from api.schemas.backtest import NavComparisonResponse, ReturnsResponse, ReturnsScatterSeries
from api.serialization.frames import df_to_series, nan_to_none, to_iso
from api.services import summaries

# Benchmarks the NAV chart overlays (matches nav_comparison.py).
BENCHMARK_TICKERS = ("TLT", "AGG", "SHY")

# Round the dense returns scatter to trim wire size (§6); ~8dp is lossless visually.
_RETURNS_ROUND_DP = 8


def _filter_scenarios(results: pd.DataFrame, scenario_ids: list[str] | None) -> pd.DataFrame:
    """Restrict to the requested scenario ids (all when ``None``)."""
    if scenario_ids:
        return results[results["scenario_id"].isin(scenario_ids)]
    return results


def get_nav_comparison(
    scenario_ids: list[str] | None = None,
    benchmarks: list[str] | None = None,
) -> NavComparisonResponse:
    """Scenario NAV lines + dashed B&H benchmark lines + performance summary (Tab 1)."""
    results = _filter_scenarios(get_backtest_results(), scenario_ids)
    scenarios = sorted(results["scenario_id"].unique())

    scenario_series = [
        df_to_series(
            results[results["scenario_id"] == sid].sort_values("date"),
            name=f"Scenario: {sid}",
            x="date",
            y="nav",
        )
        for sid in scenarios
    ]

    # Benchmark window + scaling base, replicating nav_comparison.py.
    if scenarios:
        start_ts = results["date"].min()
        start_date = start_ts.strftime("%Y-%m-%d") if pd.notna(start_ts) else None
        first_scenario = results[results["scenario_id"] == scenarios[0]].sort_values("date")
        initial_nav = float(first_scenario["nav"].iloc[0])
    else:
        start_ts = None
        start_date = None
        initial_nav = 1_000_000.0

    wanted = [b for b in (benchmarks or BENCHMARK_TICKERS) if b in BENCHMARK_TICKERS]
    if not wanted:
        wanted = list(BENCHMARK_TICKERS)

    benchmark_series = []
    if start_ts is not None:
        etf = get_etf_history(wanted)
        for ticker in wanted:
            tdf = etf[etf["ticker"] == ticker].sort_values("date")
            tdf = tdf[tdf["date"] >= start_ts]
            if tdf.empty:
                continue
            bh = summaries.buy_and_hold_nav(tdf[["date", "close"]], initial_nav)
            benchmark_series.append(
                df_to_series(bh, name=f"B&H: {ticker}", x="date", y="nav", meta={"dash": "dash"})
            )

    return NavComparisonResponse(
        start_date=start_date,
        initial_nav=initial_nav,
        scenario_series=scenario_series,
        benchmark_series=benchmark_series,
        summary=summaries.nav_summary_rows(results),
    )


def get_returns(scenario_ids: list[str] | None = None) -> ReturnsResponse:
    """Daily-return scatter per scenario, columnar form for the WebGL plot (Tab 2)."""
    results = _filter_scenarios(get_backtest_results(), scenario_ids)
    scenarios = sorted(results["scenario_id"].unique())

    series = []
    for sid in scenarios:
        sdf = results[results["scenario_id"] == sid].sort_values("date")
        dates = to_iso(sdf["date"]).tolist()
        returns = []
        for value in sdf["ret"].tolist():
            clean = nan_to_none(value)
            returns.append(round(clean, _RETURNS_ROUND_DP) if isinstance(clean, float) else None)
        series.append(ReturnsScatterSeries(scenario_id=str(sid), dates=dates, returns=returns))

    return ReturnsResponse(series=series)
