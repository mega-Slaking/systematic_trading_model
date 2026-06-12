"""Strategy-registry schemas (spec endpoint 12).

Read-only introspection of ``src/strategy/presets.py:STRATEGIES`` so the UI can
show what each opaque ``scenario_id`` means (it does not let the UI *change* the
live strategy).
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
    is_live: bool  # name == presets.LIVE_STRATEGY


class StrategiesResponse(BaseModel):
    """The whole registry plus the currently-selected live strategy name."""

    live_strategy: str
    strategies: list[StrategySummary]
