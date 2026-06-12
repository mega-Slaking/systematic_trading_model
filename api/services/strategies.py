"""Strategies service (spec endpoint 12).

Read-only introspection of the ``STRATEGIES`` registry: flatten each
``StrategyConfig``'s nested sub-configs into a summary so the UI can decode the
opaque ``scenario_id`` names. Does not mutate or select the live strategy.
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

from src.strategy.presets import LIVE_STRATEGY, STRATEGIES

from api.schemas.strategy import StrategiesResponse, StrategySummary


def get_strategies() -> StrategiesResponse:
    """Flatten the registry into per-strategy summaries."""
    summaries = [
        StrategySummary(
            name=name,
            description=config.description,
            starting_weight_source=config.sizing.starting_weight_source,
            use_vol_scaling=bool(config.sizing.use_vol_scaling),
            vol_scaling_power=float(config.sizing.vol_scaling_power),
            use_covariance_scaling=bool(config.sizing.use_covariance_scaling),
            target_portfolio_vol=float(config.sizing.target_portfolio_vol),
            cov_method=config.covariance.method,
            is_live=(name == LIVE_STRATEGY),
        )
        for name, config in STRATEGIES.items()
    ]
    return StrategiesResponse(live_strategy=LIVE_STRATEGY, strategies=summaries)
