"""Named registry of concrete strategy configs (``STRATEGIES``).

A flat dict of concrete, named ``StrategyConfig`` objects so the backtest can
iterate ``STRATEGIES.values()`` and (later) live can select a single entry by
name. Built from ``grid(...)`` helpers that re-express the five
``src/scenarios/factory.py`` builders declaratively.

See docs/strategy_config_design_spec.md (V1.10.0).
"""

import itertools
import json
from pathlib import Path

from src.strategy.config import StrategyConfig


# Building blocks
DEFAULT_STRATEGY = StrategyConfig(name="default")
BASE_V1   = DEFAULT_STRATEGY.with_(name="baseV1")
LEGACY_V1 = DEFAULT_STRATEGY.with_(name="legacyBase", starting_weight_source="legacy")


def grid(base: StrategyConfig, *, name: str, labels=None, **axes) -> list[StrategyConfig]:
    """List-valued knobs become a cartesian sweep; scalars are held fixed.

    `labels` optionally maps {knob: fn(value)->str} for tidy names (e.g. tv03).
    """
    labels = labels or {}
    list_axes = {k: v for k, v in axes.items() if isinstance(v, (list, tuple))}
    fixed     = {k: v for k, v in axes.items() if k not in list_axes}
    keys = list(list_axes)
    out = []
    for combo in itertools.product(*(list_axes[k] for k in keys)):
        parts = [labels.get(k, lambda v: f"{k}{v}")(v) for k, v in zip(keys, combo)]
        out.append(base.with_(name="_".join([name, *parts]), **fixed, **dict(zip(keys, combo))))
    return out


def _registry(*families) -> dict[str, StrategyConfig]:
    out: dict[str, StrategyConfig] = {}
    for fam in families:
        for s in fam:
            if s.name in out:
                raise ValueError(f"Duplicate strategy name: {s.name}")
            out[s.name] = s
    return out


_tv  = {"target_portfolio_vol": lambda v: f"tv{int(round(v*100)):02d}"}
_lam = {"cov_ewma_lambda":      lambda v: f"lam{int(round(v*100)):02d}"}

STRATEGIES = _registry(
    # The live-equivalent config (StrategyConfig() defaults). Never previously
    # backtested; including it here is the one intentional addition (22 -> 23).
    [DEFAULT_STRATEGY],

    # build_vol_power_scenarios()  -> 1  (name: baseV1_roll20_p001)
    # NOTE 1: vol_scaling_power is passed as a single-element LIST so grid() treats
    # it as a swept axis and appends the "p001" label -> "baseV1_roll20_p001".
    # (The spec's section 4.2 grid passed it as a scalar, which would NOT have
    # produced the p001 suffix and would have mis-named this scenario.)
    # NOTE 2: the factory's build_vol_power_scenarios omits use_covariance_scaling,
    # so build_scenario's default (False) applies. We set it explicitly here to
    # stay field-identical to the factory (the spec's section 4.2 grid omitted it,
    # which would have inherited PositionSizingConfig()'s True and silently turned
    # covariance scaling ON for this live scenario).
    grid(BASE_V1, name="baseV1_roll20", use_vol_scaling=True,
         vol_scaling_power=0.0, use_covariance_scaling=False,
         labels={"vol_scaling_power": lambda v: f"p{int(round(v*100)):03d}"}),

    # build_covariance_scaling_scenarios()  -> 3
    # vol_scaling_power=0.0 added (vs the spec grid) to match the factory field-for-
    # field. It is behaviorally dead here because use_vol_scaling=False.
    grid(BASE_V1, name="baseV1_roll20_covlb20", use_vol_scaling=False,
         vol_scaling_power=0.0,
         use_covariance_scaling=True, cov_method="sample_cov", cov_lookback_days=20,
         target_portfolio_vol=[0.03, 0.05], labels=_tv),

    # build_ewma_covariance_scaling_scenarios()  -> 8
    # vol_scaling_power=0.0 added to match the factory (dead: use_vol_scaling=False).
    # vol_ewma_lambda is intentionally NOT set (spec section 4.1): the factory fed one
    # ewma_lambda to both vol+cov, but vol_method="rolling_std" ignores it, so only
    # cov_ewma_lambda matters. Behavior-preserving; vol's ewma_lambda stays default.
    grid(BASE_V1, name="baseV1_roll20_ewmacov", use_vol_scaling=False,
         vol_scaling_power=0.0,
         use_covariance_scaling=True, cov_method="ewma_cov",
         cov_ewma_lambda=[0.94, 0.97], target_portfolio_vol=[ 0.03, 0.05],
         labels={**_lam, **_tv}),

    # build_legacy_ewma_covariance_scaling_scenarios()  -> 8
    grid(LEGACY_V1, name="legacyBase_roll20_ewmacov", use_vol_scaling=False,
         vol_scaling_power=0.0,
         use_covariance_scaling=True, cov_method="ewma_cov",
         cov_ewma_lambda=[0.94, 0.97], target_portfolio_vol=[0.02, 0.03, 0.04, 0.05],
         labels={**_lam, **_tv}),

    # build_legacy_covariance_scaling_scenarios()  -> 2
    grid(LEGACY_V1, name="legacyBase_roll20_covlb20", use_vol_scaling=False,
         vol_scaling_power=0.0,
         use_covariance_scaling=True, cov_method="sample_cov", cov_lookback_days=20,
         target_portfolio_vol=[0.03, 0.05], labels=_tv),
)


# ---------------------------------------------------------------------------
# Live selection (spec step 5). The live run trades exactly ONE registry entry.
# LIVE_STRATEGY is the built-in default; it can be overridden at runtime by a
# small JSON file (data/live_strategy.json) written from the dashboard's
# Strategies tab. The override always takes precedence when set and valid; a
# "reset to default" clears the file and falls back to this constant.
# ---------------------------------------------------------------------------
LIVE_STRATEGY = "baseV1_roll20_ewmacov_lam94_tv05"

# data/live_strategy.json at the repo root (src/strategy/presets.py -> parents[2]).
_OVERRIDE_PATH = Path(__file__).resolve().parents[2] / "data" / "live_strategy.json"


def live_strategy_override() -> str | None:
    """The dashboard-selected live strategy name, or None if unset/invalid.

    Reads the override file on every call (cheap) so the API and the live run
    always see the latest selection. Anything malformed — missing file, bad JSON,
    a non-object top level, or a name that isn't a registry key — is treated as no
    override, so we fall back to the constant rather than crash the live run.
    """
    try:
        with open(_OVERRIDE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    name = data.get("live_strategy")
    return name if isinstance(name, str) and name in STRATEGIES else None


def effective_live_strategy_name() -> str:
    """The name the live run will trade: the override if set, else the constant."""
    return live_strategy_override() or LIVE_STRATEGY


def set_live_strategy_override(name: str) -> None:
    """Persist `name` as the live selection (must be a registry key)."""
    if name not in STRATEGIES:
        raise KeyError(
            f"{name!r} is not in STRATEGIES. Available: {sorted(STRATEGIES)}"
        )
    _OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_OVERRIDE_PATH, "w", encoding="utf-8") as fh:
        json.dump({"live_strategy": name}, fh, indent=2)


def clear_live_strategy_override() -> None:
    """Remove the override file, reverting the live run to the LIVE_STRATEGY constant."""
    _OVERRIDE_PATH.unlink(missing_ok=True)


def live_strategy() -> StrategyConfig:
    """Return the StrategyConfig the live run should trade.

    Honours the runtime override (data/live_strategy.json) when set, otherwise the
    LIVE_STRATEGY constant. Fails fast (listing the available names) if the chosen
    name is not a registry key, so a typo can never silently fall back to default.
    """
    name = effective_live_strategy_name()
    try:
        # return STRATEGIES[LIVE_STRATEGY]  # pre-override behaviour (constant only)
        return STRATEGIES[name]
    except KeyError:
        raise KeyError(
            f"live strategy {name!r} is not in STRATEGIES. "
            f"Available: {sorted(STRATEGIES)}"
        ) from None
