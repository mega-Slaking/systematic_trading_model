"""Tearsheet service (spec endpoint 5) -- the one real compute path.

Loads the same three frames the Streamlit tab loads, calls ``build_tearsheet``
**unchanged**, computes the regime-match-rate caption, and serializes the result.
The output is cached on ``(scenario_id, risk_free_rate, periods_per_year)`` (§5.2)
since ``build_tearsheet`` is a deterministic pure function of immutable DB state.

Raises ``LookupError`` for an unknown scenario (router -> 404); ``build_tearsheet``
raises ``ValueError`` for other bad input (router -> 422, §10.9).
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

import pandas as pd

from accounting.tearsheet_builder import build_tearsheet
from src.storage.db_reader import get_backtest_regime_trace, get_backtest_results, get_etf_history

from api.cache import TTLCache
from api.config import get_settings
from api.schemas.tearsheet import TearsheetResponse
from api.serialization.dataclasses import tearsheet_to_response

_cache: TTLCache | None = None


def _tearsheet_cache() -> TTLCache:
    """Process-wide tearsheet cache (lazily built with the configured TTL)."""
    global _cache
    if _cache is None:
        _cache = TTLCache(get_settings().tearsheet_cache_ttl_seconds)
    return _cache


def _regime_match_rate(results: pd.DataFrame, regime: pd.DataFrame) -> float | None:
    """Fraction of scenario rows that matched a regime row (the tab's debug caption).

    Reproduces ``tearsheet.py``: left-merge results onto the regime trace on
    ``(date, scenario_id)`` and take ``inflation_regime.notna().mean()``.
    """
    if regime.empty or "inflation_regime" not in regime.columns:
        return None
    merged = results.merge(regime, on=["date", "scenario_id"], how="left")
    if "inflation_regime" not in merged.columns:
        return None
    return float(merged["inflation_regime"].notna().mean())


def get_tearsheet(
    scenario_id: str,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> TearsheetResponse:
    """Build (or serve cached) the full tearsheet for one scenario."""
    cache = _tearsheet_cache()
    key = (scenario_id, risk_free_rate, periods_per_year)
    cached = cache.get(key)
    if cached is not None:
        return cached

    results = get_backtest_results(scenario_id).sort_values("date").reset_index(drop=True)
    if results.empty:
        raise LookupError(scenario_id)

    regime = get_backtest_regime_trace(scenario_id)
    benchmark_prices = get_etf_history()

    # build_tearsheet is unchanged engine compute; it raises ValueError on bad input.
    result = build_tearsheet(
        results_df=results,
        regime_df=regime,
        benchmark_prices_df=benchmark_prices,
        risk_free_rate=risk_free_rate,
        periods_per_year=periods_per_year,
    )

    response = tearsheet_to_response(result, _regime_match_rate(results, regime))
    cache.set(key, response)
    return response
