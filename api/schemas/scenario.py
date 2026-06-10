"""Scenario-list schema (spec endpoint 1).

The distinct scenario ids persisted in ``backtest_results`` -- the picker + count
the app shell shows (replaces the Streamlit ``len(scenarios)`` line). These are
the *persisted* run tags, not the live ``StrategyConfig`` registry.
"""

from __future__ import annotations

from pydantic import BaseModel


class ScenariosResponse(BaseModel):
    """Distinct persisted scenario ids (sorted) plus their count."""

    scenarios: list[str]
    count: int
