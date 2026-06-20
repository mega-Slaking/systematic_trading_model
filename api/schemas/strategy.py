"""Strategy-registry schemas (spec endpoint 12).

Introspection of ``src/strategy/presets.py:STRATEGIES`` so the UI can show what
each opaque ``scenario_id`` means, plus a small write path so the dashboard can
select which registry entry the live run trades (a runtime override over the
``LIVE_STRATEGY`` constant; see ``presets.live_strategy_override``).
"""

from __future__ import annotations

from pydantic import BaseModel


class StrategySummary(BaseModel):
    """A flattened view of one ``StrategyConfig`` (selected knobs from its sub-configs)."""

    name: str
    description: str | None
    starting_weight_source: str  # "conviction" | "legacy"
    use_vol_scaling: bool
    vol_scaling_power: float
    use_covariance_scaling: bool
    target_portfolio_vol: float
    cov_method: str
    is_live: bool  # name == the effective live strategy (override or constant)


class StrategiesResponse(BaseModel):
    """The whole registry plus the currently-selected live strategy name."""

    live_strategy: str  # the effective selection (override if set, else the constant)
    default_strategy: str  # the LIVE_STRATEGY built-in default
    is_overridden: bool  # True when a dashboard override is active
    strategies: list[StrategySummary]


class SetLiveStrategyRequest(BaseModel):
    """Body of ``POST /strategies/live``: the registry name to make live."""

    name: str
