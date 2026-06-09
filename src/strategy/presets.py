"""Named registry of concrete strategy configs (``STRATEGIES``).

A flat dict of concrete, named ``StrategyConfig`` objects so the backtest can
iterate ``STRATEGIES.values()`` and (later) live can select a single entry by
name. Built from ``grid(...)`` helpers that re-express the five
``src/scenarios/factory.py`` builders declaratively.

See docs/strategy_config_design_spec.md (V1.10.0).
"""

import itertools

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
# Change this single line to switch the live book; it must name a key in
# STRATEGIES (enforced by live_strategy()).
# ---------------------------------------------------------------------------
LIVE_STRATEGY = "baseV1_roll20_ewmacov_lam94_tv05"


def live_strategy() -> StrategyConfig:
    """Return the StrategyConfig the live run should trade.

    Fails fast (listing the available names) if LIVE_STRATEGY is not a registry
    key, so a typo can never silently fall back to a different or default book.
    """
    try:
        return STRATEGIES[LIVE_STRATEGY]
    except KeyError:
        raise KeyError(
            f"LIVE_STRATEGY={LIVE_STRATEGY!r} is not in STRATEGIES. "
            f"Available: {sorted(STRATEGIES)}"
        ) from None
