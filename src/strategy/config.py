"""Unified, composed strategy configuration (single source of truth).

`StrategyConfig` composes the five existing sub-configs (it does not replace
them) and adds the two that were previously unreachable from `run_engine`
(`conviction`, `constraints`). This is the config-side peer to the V1.9.5
`EngineContext` Protocol: the Protocol unified the *interface*; this unifies the
*config*.

See docs/strategy_config_design_spec.md (V1.10.0).
"""

from dataclasses import dataclass, field, replace

from src.volatility.models import VolatilityConfig
from src.covariance.models import CovarianceConfig
from src.decision.position_sizer_engine import PositionSizingConfig
from src.conviction.models import ConvictionConfig
from src.decision.constraints import WeightConstraints


# Flat knob name -> (sub-config attr, field on that sub-config).
# Lets .with_() flip a knob without the caller knowing which nested object owns it.
# Adding a new sweepable knob is a single line here (see spec section 5).
_FIELD_OWNERS = {
    "vol_method":             ("volatility", "method"),
    "vol_lookback_days":      ("volatility", "lookback_days"),
    "vol_ewma_lambda":        ("volatility", "ewma_lambda"),
    "cov_method":             ("covariance", "method"),
    "cov_lookback_days":      ("covariance", "lookback_days"),
    "cov_ewma_lambda":        ("covariance", "ewma_lambda"),
    "use_vol_scaling":        ("sizing", "use_vol_scaling"),
    "vol_scaling_power":      ("sizing", "vol_scaling_power"),
    "use_covariance_scaling": ("sizing", "use_covariance_scaling"),
    "target_portfolio_vol":   ("sizing", "target_portfolio_vol"),
    "target_gross":           ("sizing", "target_gross"),
    "max_asset_weight":       ("sizing", "max_asset_weight"),
    "starting_weight_source": ("sizing", "starting_weight_source"),
    "shy_floor":              ("constraints", "shy_floor"),
}


@dataclass(frozen=True)
class StrategyConfig:
    name: str = "default"
    description: str | None = None
    volatility:  VolatilityConfig     = field(default_factory=VolatilityConfig)
    covariance:  CovarianceConfig     = field(default_factory=CovarianceConfig)
    sizing:      PositionSizingConfig = field(default_factory=PositionSizingConfig)
    conviction:  ConvictionConfig     = field(default_factory=ConvictionConfig)
    constraints: WeightConstraints    = field(default_factory=WeightConstraints)

    def with_(self, *, name: str | None = None, **overrides) -> "StrategyConfig":
        """Return a copy with individual knobs flipped, routed to the right sub-config."""
        grouped: dict[str, dict] = {}
        for key, value in overrides.items():
            if key not in _FIELD_OWNERS:
                raise KeyError(f"Unknown strategy knob: {key!r}")
            sub, fld = _FIELD_OWNERS[key]
            grouped.setdefault(sub, {})[fld] = value
        patched = {sub: replace(getattr(self, sub), **kw) for sub, kw in grouped.items()}
        return replace(self, name=name or self.name, **patched)
