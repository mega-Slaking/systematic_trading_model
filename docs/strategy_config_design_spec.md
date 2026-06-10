# Design Spec: Unified, Selectable Strategy Configuration

**Status:** Proposal (no code changes yet)
**Target version:** V1.10.0 (backward-compatible feature)
**Author:** drafted with quant-engineer analysis
**Date:** 2026-06-08

---

## 1. Purpose

Make it fast and safe to experiment with strategy variants — toggling risk
features (covariance scaling, volatility scaling, etc.) on and off — and let a
**single named registry of strategy configs** drive **both** the backtest sweep
and the live run, so that *what trades live is always one of the configs we
backtested*.

Goal experience:

```python
# Try a variant in one line, no factory edits:
exp = DEFAULT_STRATEGY.with_(use_covariance_scaling=False)

# Backtest runs the whole registry; live picks ONE entry by name:
LIVE_STRATEGY = "baseV1_roll20_covlb20_tv05"
```

This spec is descriptive only. It proposes the design, the migration steps, and
the verification strategy. It changes no source code.

---

## 2. How configuration works today

There is **no external config layer** — no YAML/TOML/JSON, no CLI parsing, no
settings framework. Strategy configuration is Python dataclasses constructed in
code, and the backtest and live paths build them in *completely different* ways.

### 2.1 The config dataclasses (the actual knobs)

| Config | File | Frozen? | Holds |
|---|---|---|---|
| `PositionSizingConfig` | `src/decision/position_sizer_engine.py:13-23` | no | **all the risk toggles**: `use_vol_scaling`, `vol_scaling_power`, `use_covariance_scaling`, `target_portfolio_vol`, `target_gross`, `max_asset_weight`, `min_vol`, `starting_weight_source`, `fallback_to_base_if_empty` |
| `VolatilityConfig` | `src/volatility/models.py:9-21` | yes | point-in-time vol estimator (method, lookback, ewma_lambda, garch params) |
| `CovarianceConfig` | `src/covariance/models.py:9-16` | no | covariance estimator (method, lookback, ewma params) |
| `ConvictionConfig` | `src/conviction/models.py:4-25` | no | conviction multipliers/weights/sensitivity |
| `WeightConstraints` | `src/decision/constraints.py:7-23` | yes | `shy_floor`, per-asset caps/floors, eligibility, fallback |
| `BacktestScenario` | `src/scenarios/models.py:8-15` | yes | bundles vol+cov+sizing + `scenario_id` + `description` + (dead) `base_allocation_profile` |

### 2.2 The fork: `run_engine`

Everything funnels through `run_engine(context, scenario=None)` at
`src/engine/run.py:15`. The config fork is `src/engine/run.py:28-45`:

- **Backtest** (`scenario` provided): reads `scenario.volatility_config`,
  `scenario.covariance_config`, `scenario.position_sizing_config`.
- **Live** (`scenario is None`): hardcodes a `VolatilityConfig` and
  `CovarianceConfig` inline, and sets `sizing_config = None`. A `None` sizing
  config makes `size_positions` build a default `PositionSizingConfig()`
  (`position_sizer_engine.py:197`).

The backtest engine drives the same function once per day:
`src/backtest/engine.py:82` → `run_engine(context, scenario=scenario)`.

### 2.3 Two config objects are silently unreachable

`orchestrate_decision_pipeline` *accepts* `conviction_config` and `constraints`
(`src/engine/decision_orchestration.py:14,18`), but `run_engine` never passes
them (`src/engine/run.py:80-87`). So on **every** run — backtest and live — both
fall through to `None`:

- `apply_conviction_scaling(config=None)` → `ConvictionConfig()`
  (`src/conviction/engine.py:221`)
- `apply_final_constraints(constraints=None)` → `WeightConstraints()`
  (`src/decision/constraint_engine.py:41`)

**Consequence:** today you cannot sweep the SHY floor, eligibility, or any
conviction parameter — the plumbing exists but is never fed. (This also means
passing the *explicit defaults* later is byte-identical to the current `None`
behavior — the lever that makes the migration safe; see §7.)

### 2.4 The hidden divergence between backtest and live

The single most important problem. Compare the **default backtest scenario**
(`build_scenario(...)`, `src/scenarios/factory.py:7-27`) with **what live
actually runs** (`sizing_config=None` → `PositionSizingConfig()` defaults):

| knob | `build_scenario()` default | live today (`PositionSizingConfig()`) |
|---|---|---|
| `use_vol_scaling` | `True` | `True` |
| `vol_scaling_power` | **`0.0`** → vol scaling is a *no-op* (`w / vol**0 = w`) | **`0.20`** → real vol scaling |
| `use_covariance_scaling` | **`False`** | **`True`** |
| `target_portfolio_vol` | `0.10` (unused, cov off) | `0.10` (active) |
| `starting_weight_source` | `"conviction"` | `"conviction"` |

So **live silently applies vol-power-0.20 + covariance scaling to a 10% vol
target with a SHY buffer**, while the vanilla backtest does *no* risk scaling.
And none of the five builders wired into `run_backtest.py:85-95` use
`vol_scaling_power=0.20` (they use `0.0` or `0.01`). **The exact sizing the live
book uses is validated by zero backtest scenarios.** Unifying config so live
*selects a backtested entry* is what structurally closes this gap.

### 2.5 Where experimentation friction comes from today

1. Toggling covariance scaling requires editing Python — there is no single
   switch. You edit a builder body or change which builders are summed in
   `run_backtest.py:85-95`.
2. `build_scenario` is a 20-argument flat factory (`factory.py:7-27`) that
   flattens three nested configs; param names don't always match dataclass
   fields, and `ewma_lambda` is fed to **both** vol and cov configs
   (`factory.py:35,42`).
3. Magic numbers are scattered: target-vol grids (`factory.py:79,113,151,189`),
   `2014-01-01` start and `1_000_000` capital (`run_backtest.py:50,100`), and a
   third home for cost/trade knobs in `config.py:19-35`.
4. Defaults disagree for the *same* knob: `use_covariance_scaling` defaults to
   `True` in the dataclass (`position_sizer_engine.py:21`) but `False` in the
   factory (`factory.py:22`).

---

## 3. Investigation: `base_allocation_profile` (the "dead knob")

Requested explicitly before any change is considered. **Finding: it is an inert
string label with no functional link to the legacy pipeline.**

### 3.1 What the legacy pipeline actually is

`build_pre_risk_decision` (`src/decision/pipeline.py:10-32`) runs an identical,
**unconditional** sequence every time, regardless of any config:

1. `evaluate_regime`
2. `allocate_legacy_base_weights` → sets `decision.legacy_base_weights`
   (`src/legacy/legacy_base_weight_allocation.py:18`)
3. `determine_favourable_assets` → sets `decision.direction`
4. `allocate_base_weights` → sets `decision.base_weights`
   (`src/decision/base_allocator_engine.py:17`)
5. `apply_conviction_scaling` → sets `decision.conviction_weights`

So **both** the legacy allocator and the modern base allocator always run and
produce two parallel weight vectors. Which one is *used* is decided downstream by
`starting_weight_source` in `PositionSizingConfig`
(`src/decision/position_sizer_engine.py:43-77`):

- `"conviction"` → start from `conviction_weights` (modern path)
- `"legacy"` → start from `legacy_base_weights` (legacy path)

### 3.2 What `base_allocation_profile` does: nothing

All 9 occurrences (grep-confirmed) are **writes or declarations — zero reads**:

- declared on `Decision` (`src/decision/models.py:28`, default `None`) — but
  **never assigned** anywhere, so it is always `None`
- declared on `BacktestScenario` (`src/scenarios/models.py:15`)
- threaded through `build_scenario` (`src/scenarios/factory.py:25,53`)
- set to `"baseV1"` / `"legacy_signal_weighted"` / `"current"` in the builders
  (`factory.py:71,100,137,176,211`)

It is **not** read by the pipeline, the allocators, `run_engine`, the storage
layer, or any visual/tearsheet. In the builders it merely *covaries* with
`starting_weight_source="legacy"` as a human-readable tag, but only
`starting_weight_source` has any effect.

### 3.3 Conclusion

`base_allocation_profile` is a documentation label that *shadows* the meaning of
`starting_weight_source` without driving anything. **Decision: leave it for now.**
It is safe to retire later (removing it changes no behavior) or to promote into a
real allocator selector if a genuine second base-allocation profile is wanted —
but that is out of scope for this spec.

---

## 4. Proposed design

Stay inside the existing **dataclass + factory** idiom. No pydantic, no YAML
runtime dependency, no argparse framework. Three additive pieces.

### 4.1 `StrategyConfig` — one composed config (single source of truth)

A new `src/strategy/config.py`. It *composes* the five existing sub-configs (does
not replace them) and adds the two that were unreachable (`conviction`,
`constraints`). This is the config-side peer to the V1.9.5 `EngineContext`
Protocol: the Protocol unified the *interface*; this unifies the *config*.

```python
from dataclasses import dataclass, field, replace
from src.volatility.models import VolatilityConfig
from src.covariance.models import CovarianceConfig
from src.decision.position_sizer_engine import PositionSizingConfig
from src.conviction.models import ConvictionConfig
from src.decision.constraints import WeightConstraints

# Flat knob name -> (sub-config attr, field on that sub-config).
# Lets .with_() flip a knob without the caller knowing which nested object owns it.
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
```

Notes:

- **`default_factory` for every sub-config** (even the frozen ones) avoids the
  shared-mutable-default footgun: three of the five (`PositionSizingConfig`,
  `CovarianceConfig`, `ConvictionConfig`) are not frozen.
- **`ewma_lambda` split** into `vol_ewma_lambda` / `cov_ewma_lambda`. The current
  factory feeds one value to both (`factory.py:35,42`); splitting is clearer and
  **behavior-preserving** for the existing EWMA builders because they pair
  `vol_method="rolling_std"` (ignores `ewma_lambda`) with `cov_method="ewma_cov"`
  — only the cov side ever mattered.
- `dataclasses.replace` works on frozen and non-frozen alike, so `.with_()` is
  uniform.

### 4.2 The registry — `STRATEGIES` (replaces the factory builders)

A new `src/strategy/presets.py`. A **flat dict of concrete, named configs** so
the backtest can iterate `STRATEGIES.values()` and live can select any single
entry by name. Built from `grid(...)` helpers that re-express the current five
builders declaratively.

```python
import itertools
from src.strategy.config import StrategyConfig

# Building blocks
DEFAULT_STRATEGY = StrategyConfig(name="default")
BASE_V1   = DEFAULT_STRATEGY.with_(name="baseV1")
LEGACY_V1 = DEFAULT_STRATEGY.with_(name="legacyBase", starting_weight_source="legacy")

def grid(base: StrategyConfig, *, name: str, labels=None, **axes) -> list[StrategyConfig]:
    """List-valued knobs become a cartesian sweep; scalars are held fixed.
    `labels` optionally maps {knob: fn(value)->str} for tidy names (e.g. tv03)."""
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
    [DEFAULT_STRATEGY],

    # build_vol_power_scenarios()  -> 1
    # vol_scaling_power is a single-element LIST so grid() treats it as a swept axis
    # and appends the "p001" label; use_covariance_scaling=False is explicit to match
    # the factory (otherwise it would inherit PositionSizingConfig()'s True).
    grid(BASE_V1, name="baseV1_roll20", use_vol_scaling=True,
         vol_scaling_power=[0.01], use_covariance_scaling=False,
         labels={"vol_scaling_power": lambda v: f"p{int(round(v*100)):03d}"}),

    # build_covariance_scaling_scenarios()  -> 3
    grid(BASE_V1, name="baseV1_roll20_covlb20", use_vol_scaling=False,
         use_covariance_scaling=True, cov_method="sample_cov", cov_lookback_days=20,
         target_portfolio_vol=[0.03, 0.05, 0.07], labels=_tv),

    # build_ewma_covariance_scaling_scenarios()  -> 8
    grid(BASE_V1, name="baseV1_roll20_ewmacov", use_vol_scaling=False,
         use_covariance_scaling=True, cov_method="ewma_cov",
         cov_ewma_lambda=[0.94, 0.97], target_portfolio_vol=[0.02, 0.03, 0.04, 0.05],
         labels={**_lam, **_tv}),

    # build_legacy_ewma_covariance_scaling_scenarios()  -> 8
    grid(LEGACY_V1, name="legacyBase_roll20_ewmacov", use_vol_scaling=False,
         use_covariance_scaling=True, cov_method="ewma_cov",
         cov_ewma_lambda=[0.94, 0.97], target_portfolio_vol=[0.02, 0.03, 0.04, 0.05],
         labels={**_lam, **_tv}),

    # build_legacy_covariance_scaling_scenarios()  -> 2
    grid(LEGACY_V1, name="legacyBase_roll20_covlb20", use_vol_scaling=False,
         use_covariance_scaling=True, cov_method="sample_cov", cov_lookback_days=20,
         target_portfolio_vol=[0.03, 0.05], labels=_tv),
)
```

This reproduces all **22** scenarios the current builders emit, but every entry
is independently nameable and selectable.

> Mapping to current builders (`src/scenarios/factory.py`): `build_vol_power_scenarios`
> → 1, `build_covariance_scaling_scenarios` → 3, `build_ewma_covariance_scaling_scenarios`
> → 8, `build_legacy_ewma_covariance_scaling_scenarios` → 8,
> `build_legacy_covariance_scaling_scenarios` → 2.

### 4.3 Live selection

Live picks **one** entry from the same registry — one git-tracked, reviewable
line, and the same object the backtest validated:

```python
# in src/strategy/presets.py
LIVE_STRATEGY = "baseV1_roll20_covlb20_tv05"   # the live book

def live_strategy() -> StrategyConfig:
    return STRATEGIES[LIVE_STRATEGY]
```

`main.py` then passes it explicitly:

```python
from src.strategy.presets import live_strategy
run_engine(context, strategy=live_strategy())
```

Optional sugar (later): a `--strategy NAME` CLI override on `main.py` that
defaults to `LIVE_STRATEGY`.

### 4.4 `run_engine` resolution

`run_engine` gains an optional `strategy` and resolves all three inputs through
one helper, then forwards conviction + constraints (the §2.3 fix):

```python
def resolve_strategy(scenario=None, strategy=None) -> StrategyConfig:
    if strategy is not None:
        return strategy
    if scenario is not None:                      # back-compat lift of a BacktestScenario;
        return StrategyConfig(                     # conviction/constraints stay default == old None
            name=scenario.scenario_id, description=scenario.description,
            volatility=scenario.volatility_config,
            covariance=scenario.covariance_config,
            sizing=scenario.position_sizing_config)
    return STRATEGIES["default"]

def run_engine(context, scenario=None, strategy=None):
    ...
    strategy = resolve_strategy(scenario=scenario, strategy=strategy)
    vol_config, cov_config = strategy.volatility, strategy.covariance
    ...
    decision = orchestrate_decision_pipeline(
        decision=Decision(date=context.current_date.isoformat()),
        price_signals=price_signals, macro_signals=macro_signals,
        conviction_config=strategy.conviction,    # NEW (was implicitly None)
        vol_estimate=vol_estimate, cov_estimate=cov_estimate,
        sizing_config=strategy.sizing,
        constraints=strategy.constraints,          # NEW (was implicitly None)
    )
```

The backtest engine (`src/backtest/engine.py:59,82`) gains `strategy=None` and
forwards it: `run_engine(context, scenario=scenario, strategy=strategy)`.
`run_backtest.py` iterates the registry and tags DB rows with `strategy.name`
(playing the `scenario_id` role).

---

## 5. Using it day-to-day

### 5.1 Common one-liners

```python
from src.strategy.presets import STRATEGIES, DEFAULT_STRATEGY, grid

# Toggle covariance scaling off for a one-off experiment:
exp = DEFAULT_STRATEGY.with_(name="default_covOff", use_covariance_scaling=False)

# Turn off both risk layers:
exp = DEFAULT_STRATEGY.with_(use_covariance_scaling=False, use_vol_scaling=False)

# Switch to the legacy base allocation:
exp = DEFAULT_STRATEGY.with_(starting_weight_source="legacy")

# A target-vol sweep (declarative):
sweep = grid(DEFAULT_STRATEGY, name="myidea", use_covariance_scaling=True,
             target_portfolio_vol=[0.03, 0.05, 0.07])

# Backtest the whole registry:
for strat in STRATEGIES.values():
    run_backtest(..., strategy=strat)

# Point live at a validated entry — change one string:
#   LIVE_STRATEGY = "baseV1_roll20_ewmacov_lam94_tv03"
```

### 5.2 Adding a new scenario to backtest

**Today** it takes edits in two places: extend a builder's grid or write a whole
new `build_*_scenarios()` with 20-arg `build_scenario(...)` calls
(`src/scenarios/factory.py:7-27`), **and** remember to add that function into the
`scenarios = (...)` sum at `run_backtest.py:85-95` (forget it and it silently
never runs).

**After**, `run_backtest.py` iterates `STRATEGIES.values()`, so you only ever
touch `src/strategy/presets.py` — the run script is never edited. Add an entry to
the registry:

```python
# A single new variant — specify only what differs from a base:
[DEFAULT_STRATEGY.with_(name="baseV1_covOff_shy10",
                        use_covariance_scaling=False, shy_floor=0.10)]

# A new sweep — grid() expands the cartesian product:
grid(BASE_V1, name="baseV1_roll60_covlb60",
     vol_lookback_days=60, use_vol_scaling=False,
     use_covariance_scaling=True, cov_method="sample_cov", cov_lookback_days=60,
     target_portfolio_vol=[0.03, 0.05, 0.07], labels=_tv)

# Knobs that could NOT be swept before (conviction + constraints now wired in, §2.3),
# e.g. a SHY-floor sweep:
grid(BASE_V1, name="baseV1_shyfloor", shy_floor=[0.0, 0.05, 0.10],
     labels={"shy_floor": lambda v: f"shy{int(v*100):02d}"})
```

**Throwaway experiments don't need the registry.** For a one-off, build an
ad-hoc config and pass it straight in — register it only once it's worth keeping:

```python
run_backtest(..., strategy=DEFAULT_STRATEGY.with_(name="scratch", vol_scaling_power=0.3))
```

**Run a subset, not the whole registry.** `STRATEGIES` is a plain dict, so filter
it:

```python
for name, strat in STRATEGIES.items():
    if name.startswith("legacyBase_"):   # or an explicit allow-list
        run_backtest(..., strategy=strat)
```

**Adding a brand-new knob (a new risk feature).** This is where the friction
collapses. Suppose you add a field to `PositionSizingConfig`:

- *Today:* edit the dataclass **+** add a param to `build_scenario`'s signature
  **+** its body **+** thread it through each builder that needs it.
- *After:* edit the dataclass **+** add **one line** to the `_FIELD_OWNERS` map
  (§4.1). It is then usable via `.with_(new_knob=...)` everywhere immediately.

**Naming rule.** Names must be unique — `_registry()` raises on a duplicate. This
is deliberate: `name` becomes the DB tag (replacing `scenario_id`), so a collision
would otherwise silently merge two configs' results. The guard fails fast at
startup instead.

---

## 6. Migration plan (staged; no code in this spec)

Each step is small and independently verifiable. Project convention: **comment
out old code, do not delete** (commented builders / inline live block act as the
rollback safety net).

| Step | Change | Files | Risk |
|---|---|---|---|
| 1 | Add `StrategyConfig` + `with_()` + unit tests. Nothing consumes it. | new `src/strategy/config.py`, new `tests/strategy/test_strategy_config.py` | none |
| 2 | `run_engine` forwards `conviction`+`constraints` via `resolve_strategy`; behavior-preserving (explicit defaults == old `None`). | `src/engine/run.py` (comment out old fork) | low |
| 3 | Build `STRATEGIES` registry + `grid()`; re-express the 5 builders; add registry test. | new `src/strategy/presets.py`, update `tests/strategy/test_scenarios_factory.py` | low |
| 4 | Migrate `run_backtest.py` to iterate `STRATEGIES`; backtest engine accepts/forwards `strategy`; tag DB with `strategy.name`. Comment out old builders + scenario list. | `run_backtest.py`, `src/backtest/engine.py`, `src/scenarios/factory.py` | low |
| 5 | Point live at `live_strategy()`; comment out inline live block. **Behavior change** unless `LIVE_STRATEGY` reproduces today's implicit live (see §8). | `main.py`, `src/engine/run.py` | medium (deliberate) |
| 6 (later) | Retire `BacktestScenario` / `base_allocation_profile`; optional YAML external presets. | — | deferred |

---

## 7. Behavior-preservation & testing

The two behavior-touching steps are pinned by existing regression guards:

- **Backtest determinism / identical NAV:** `tests/backtest/test_backtest_e2e.py`
  builds `build_scenario(scenario_id="test_e2e")` and asserts an identical NAV
  path across two runs. After step 2, the scenario path passes
  `ConvictionConfig()` / `WeightConstraints()` explicitly — identical to the old
  `None` (verified at `conviction/engine.py:221`, `constraint_engine.py:41`) — so
  NAV must be byte-identical.
- **Live wiring:** `tests/live/test_live_run.py` asserts a valid decision,
  `final_weights` summing to 1, and traces recorded. If `STRATEGIES["default"]`
  equals `StrategyConfig()` defaults, the live path reproduces today exactly
  (`VolatilityConfig()` = rolling_std/20, `CovarianceConfig()` = sample_cov/20,
  `PositionSizingConfig()` = power0.2 + cov-on@10% — same as the old hardcoded
  block + `sizing=None`).
- **Registry coverage:** extend `tests/strategy/test_scenarios_factory.py` (or a
  new `test_presets.py`) to assert each family's toggles and sweep sizes
  (mirroring the current `test_covariance_scaling_scenarios_cover_target_vols`
  etc.).

**Acceptance bar:** same fixture in → byte-identical output, until a step
*deliberately* changes a default (only step 5, the live selection).

---

## 8. Open decision: what should live run?

Today live *implicitly* runs `PositionSizingConfig()` defaults (vol-power-0.20 +
covariance scaling @10%), a combo **no current backtest scenario tests** (§2.4).
Under this design, live must select a **named, backtested** entry. Two ways to
roll out step 5:

1. **Continuity:** add a preset `as_live_today` that reproduces the current
   implicit live config, set `LIVE_STRATEGY = "as_live_today"` → zero live
   behavior change, but now it is finally in the backtest set and comparable.
2. **Deliberate pick:** choose a validated entry from the registry (e.g.
   `baseV1_roll20_ewmacov_lam94_tv03`) after comparing backtest results → live
   behavior changes to a vetted config.

Recommended: ship steps 1-4 first (pure plumbing + registry, no live change),
compare presets in backtests, then choose `LIVE_STRATEGY` for step 5.

---

## 9. Deferred / out of scope

- Retiring or promoting `base_allocation_profile` (§3) — leave as-is for now.
- Externalizing presets to YAML/TOML (config without code edits).
- Folding `config.py` cost/trade knobs (`SLIPPAGE_BPS`, `FEE_BPS`,
  `MIN_TRADE_NOTIONAL`, `DRIFT_TOL`) and the backtest start/capital into the same
  config surface.
- A `--strategy` CLI override for `main.py`.

---

## 10. SemVer

Steps 1-5 are a backward-compatible feature (unified config + selectable
presets) → **minor bump, V1.10.0**. Step 5's live selection is a behavior change
on the live path but not an API break, so it stays under the minor bump; if it
changes the live book it should be called out explicitly in the changelog.
