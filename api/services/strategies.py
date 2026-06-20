"""Strategies service (spec endpoint 12).

Introspection of the ``STRATEGIES`` registry (flatten each ``StrategyConfig``'s
nested sub-configs into a summary so the UI can decode the opaque ``scenario_id``
names), plus selecting which entry the live run trades via the runtime override
in ``src/strategy/presets`` (the dashboard's star toggle).
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

from src.strategy.presets import (
    LIVE_STRATEGY,
    STRATEGIES,
    clear_live_strategy_override,
    live_strategy_override,
    set_live_strategy_override,
)

from api.schemas.strategy import StrategiesResponse, StrategySummary


def get_strategies() -> StrategiesResponse:
    """Flatten the registry into per-strategy summaries (live = effective selection)."""
    # Read the override once; derive both the effective live name and the flag from it.
    override = live_strategy_override()
    live = override or LIVE_STRATEGY
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
            is_live=(name == live),
        )
        for name, config in STRATEGIES.items()
    ]
    return StrategiesResponse(
        live_strategy=live,
        default_strategy=LIVE_STRATEGY,
        is_overridden=override is not None,
        strategies=summaries,
    )


def set_live_strategy(name: str) -> StrategiesResponse:
    """Persist `name` as the live selection, then return the refreshed registry.

    Raises ``ValueError`` for an unknown name (the router maps it to a 422).
    """
    try:
        set_live_strategy_override(name)
    except KeyError as exc:
        raise ValueError(str(exc)) from None
    return get_strategies()


def reset_live_strategy() -> StrategiesResponse:
    """Clear the override (revert to the LIVE_STRATEGY constant) and refresh."""
    clear_live_strategy_override()
    return get_strategies()
