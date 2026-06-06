# Test Plan — Systematic Trading Model

Blueprint for end-to-end, unit, and regression testing of the repo. Organized by
**domain** (what behaviour is being protected), not by `src/` layout. Each domain
section lists the modules it covers, the concrete cases to assert, and the
fixtures required.

Status legend: ☐ to write · ◐ partial (exists, needs porting) · ☑ done

---

## 1. Framework & conventions

- **Runner:** `pytest` (industry standard; auto-discovery, fixtures, `parametrize`,
  markers). The current `tests/feature_surface_test.py` is a print-based `main()` —
  port it to assert-based pytest under `tests/features/`.
- **Run from repo root** so `src` imports resolve: `python -m pytest tests/` (or just
  `pytest`). May need `pip install pytest`.
- **Determinism:** every test uses fixed/seeded fixtures — no network, no live DB, no
  wall-clock dependence. External I/O (`api_fetch`, `notify`) is mocked or skipped.
- **Test types** (use markers): `unit`, `integration`, `e2e`, `regression`,
  plus cross-cutting `lookahead`.
- **Golden/regression outputs** live in `tests/fixtures/` as CSV/JSON and are
  regenerated deliberately (never auto-overwritten) when behaviour is intended to change.

### Proposed layout
```
tests/
  conftest.py                 # shared fixtures
  fixtures/                   # small datasets + golden expected outputs
  data/                       # loading, missing data, date alignment
  features/                   # volatility surface / estimators
  backtest/                   # engine, portfolio, execution, accounting mechanics
  strategy/                   # regime -> decision logic
  tearsheets/                 # performance/risk analytics
  persistence/                # DB save/load round-trips
```

### Shared fixtures (`conftest.py`)
- `synthetic_etf_history` — deterministic, seeded OHLC (`date, ticker, close`) for
  TLT/AGG/SHY over ~150 trading days. Basis for backtest/feature/data tests.
- `synthetic_macro_history` — small macro frame matching `macro_data` columns.
- `price_signals_fixture` / `macro_signals_fixture` — minimal signal frames to drive
  regime/decision tests without running the signal engines.
- `sample_prices` — `{"TLT":.., "AGG":.., "SHY":..}` dict.
- `sample_decision` — a `Decision` pre-populated to the stage under test.
- `temp_db` — `tmp_path` sqlite built via `data/db_population.create_tables` (points
  the schema at a throwaway file; never touches `data/database.db`).

---

## 2. `data/` — loading, missing data, date alignment

**Covers:** `storage/db_reader.py`, `utils/ensure_long.py`, `engine/normalize.py`,
`covariance/returns_view.py` (alignment), `volatility/feature_surface._build_returns_wide`.

| # | Case | Type | Notes |
|---|---|---|---|
| ☐ | **Price loading works** — `get_etf_history` returns `date,close,ticker`, correct dtypes, sorted | integration | uses `temp_db` seeded with known rows |
| ☐ | **Missing data handled** — ticker with no valid close → `normalize_prices` returns `None`; partial NaNs ffilled, not crashed | unit | `engine/normalize.py`, `_build_returns_wide` ffill |
| ☐ | **Date alignment** — pivot/ffill aligns tickers on a shared date index; a ticker missing a date doesn't shift others; `ensure_long` wide↔long is consistent | unit | `ensure_long`, returns_view `get_window` |
| ☐ | Returns-view window slices by `as_of_date` + lookback correctly; respects `date < as_of` | unit+lookahead | `covariance/returns_view.py` |
| ☐ | Date filtering uses `<` not `<=` (no same-day leakage) at the data layer | lookahead | mirrors `BacktestContext.fetch_*` |

---

## 3. `features/` — volatility surface & estimators

**Covers:** `volatility/feature_surface.py`, `volatility/estimator.py`,
`volatility/models.py`, `covariance/estimator.py`.

| # | Case | Type | Notes |
|---|---|---|---|
| ◐ | **Surface returns expected columns** — config → exact column set (rolling_20/60, ewma_94/97, garch, comparison cols) | regression | exists informally; assert column set |
| ◐ | **Rolling volatility has no lookahead** — surface `snapshot(t)` == point estimator with `date < t` | lookahead+regression | already proven in current script; port to asserts |
| ◐ | **EWMA behaves consistently** — matches point estimator to fp precision across dates; recursion stable | regression | port from current script |
| ◐ | **GARCH** — daily-refit reduces exactly to point estimator; monthly refit is daily-varying (roll-forward active) | regression | port from current script |
| ☐ | **Feature snapshots are date-safe** — `get_snapshot(t)` only returns rows for `t`; lag shifts values one day; missing date → empty frame | unit+lookahead | `VolatilityFeatureSurface` accessors |
| ☐ | Comparison features self-consistent — `ewma_x_to_rolling_20 == ewma_x / rolling_20` | unit | already checked in script |
| ☐ | **Covariance C++ vs Python parity** — `fast_covariance_cpp` output == pandas fallback (sample & EWMA) | regression | guards the compiled path |
| ☐ | `compute_portfolio_vol_from_covariance` = `√(wᵀΣw)`; negative var → `None`; empty cov → `None` | unit | |

> Migrate `tests/feature_surface_test.py` here as `tests/features/test_volatility_surface.py`
> with pytest asserts (drop the print/main style).

---

## 4. `backtest/` — engine, portfolio, execution, accounting mechanics

**Covers:** `backtest/engine.py`, `backtest/portfolio.py`, `execution/rebalance_v2.py`,
`accounting/valuation.py`, `accounting/metrics.py`, `utils/weights.py`.

| # | Case | Type | Notes |
|---|---|---|---|
| ☐ | **NAV starts at expected value** — fresh portfolio NAV == initial capital; day-0 snapshot == cash | unit/e2e | |
| ☐ | **Returns compound correctly** — Π(1+ret) over the run == final_nav/initial_nav (within fp tol) | e2e+regression | on `synthetic_etf_history` |
| ☐ | **Transaction costs reduce NAV** — same path with fees/slippage > 0 ends below the zero-cost run; `total_cost = fee+slippage` | unit+e2e | `metrics.compute_day_metrics`, costs in `rebalance_v2` |
| ☐ | **No trades below `min_trade_notional`** — sub-threshold deltas produce zero trades (SELL and BUY legs) | unit | `rebalance_v2` |
| ☐ | **Allocation weights sum correctly** — post-`normalize_weights` sums to 1 (or 0 if all-zero); negatives clipped | unit | `utils/weights.py` |
| ☐ | **Money invariants** — cash never < 0 on cash-limited buys; SELL-before-BUY ordering; holdings update by ±qty | unit ⚠️ | `rebalance_v2` + `portfolio.apply_trades` |
| ☐ | **Valuation** — NAV = cash + Σ units·price; missing price → `KeyError`; empty holdings → cash | unit | `accounting/valuation.py` |
| ☐ | `compute_day_metrics` — `nav_prev` None/≤0 → ret 0; turnover denom; gross notional aggregation | unit | |
| ☐ | **Backtest golden** — tiny fixture → pinned NAV series, final NAV, trade count, total cost | e2e+regression | determinism guard for refactors |
| ☐ | Drift tolerance — within `drift_tol` → no rebalance | unit | `rebalance_v2` |

---

## 5. `strategy/` — regime → decision logic

**Covers:** `decision/regime_engine.py`, `decision/favourable_asset_selection.py`,
`decision/base_allocator_engine.py`, `decision/position_sizer_engine.py`,
`decision/constraint_engine.py` + `constraints.py`, `conviction/engine.py`,
`decision/pipeline.py`, `engine/decision_orchestration.py`,
`legacy/legacy_base_weight_allocation.py`.

| # | Case | Type | Notes |
|---|---|---|---|
| ☐ | **Known regime inputs → expected decisions** — exhaustive parametrized table: all 9 regimes → exact `direction` (favourable_asset_selection) | unit+regression | pure lookup |
| ☐ | All 8 active-set combos → exact `base_weights` (base_allocator) | unit+regression | pure lookup |
| ☐ | Monetary/economic classifier truth tables (`_classify_*_regime`) | unit | parametrize macro-flag combos |
| ☐ | **Fallback/default rules** — missing prices → `data_fallback` → SHY; no clear favourable set → defensive default; all-zero weights → `fallback_ticker` | unit+regression | regime_engine + base_allocator + constraints |
| ☐ | Position sizer — vol scaling, asset caps, gross normalize, **SHY-buffer fill + no-leverage cap** (`scale=min(raw,max)`); `portfolio_vol`/`portfolio_scale` set on Decision | unit+regression | `position_sizer_engine.py` |
| ☐ | Constraints — eligibility zeroing, `shy_floor`, clip, normalize-to-1 | unit | `constraints.py` |
| ☐ | Conviction multipliers/scores on fixed inputs | unit+regression | `conviction/engine.py` |
| ☐ | **Pipeline integration** — fixed signals → full `Decision`; assert `final_weights`, `rule_id`, `regime`, gross/net | integration+regression | `orchestrate_decision_pipeline` |
| ☐ | **Growth-tilted variant holds expected assets more often** — given a growth-tilted config vs base on same fixture, assert higher avg TLT/risk weight (or chosen asset frequency) | regression | *depends on the variant existing; placeholder until strategy redesign* |

---

## 6. `tearsheets/` — performance & risk analytics

**Covers:** `accounting/tearsheet_calculator.py`, `tearsheet_builder.py`, `tearsheet_models.py`.

| # | Case | Type | Notes |
|---|---|---|---|
| ☐ | **CAGR, volatility, Sharpe, drawdown, Sortino sanity** — on a known return series with closed-form expected values (e.g. constant +x%/day → exact CAGR; symmetric series → known vol) | unit+regression | pin against hand-computed values |
| ☐ | Sharpe/Sortino use the `risk_free_rate` correctly; Sortino denom uses downside only | unit | |
| ☐ | Max drawdown / Calmar on a crafted peak→trough→recovery series | unit | |
| ☐ | VaR/CVaR historical on a known distribution | unit | |
| ☐ | **Benchmark comparison output shape** — buy-and-hold NAVs returned for TLT/AGG/SHY; aligned index; expected columns | integration | |
| ☐ | **Exposure summary matches backtest allocations** — avg asset weights from tearsheet == mean of stored backtest weights | integration+regression | ties tearsheet to engine output |
| ☐ | Regime-bucketed breakdown aligns by `date` + `scenario_id` (no mismatched rows) | integration | |

---

## 7. `persistence/` — DB save/load round-trips

**Covers:** `storage/db_writer.py`, `storage/db_reader.py`, `data/db_population.py` (schema).
(`storage/persister.py` is **live-path only** — see §9, deferred.)

| # | Case | Type | Notes |
|---|---|---|---|
| ☐ | **Scenario results save/load** — `insert_backtest_results` → `get_backtest_results` round-trips values, types, `scenario_id` | integration | `temp_db` |
| ☐ | **Decision trace persists expected fields** — written row has all expected columns with correct values | integration | `insert_backtest_decision_trace` / reader |
| ☐ | Regime trace round-trip; `macro_supports_duration` bool↔int mapping | integration | |
| ☐ | `volatility_features` round-trip — all feature cols + `config_key`; **NaN → NULL** (`_none_if_nan`); `INSERT OR REPLACE` idempotency (re-write same key, row count stable) | integration | |
| ☐ | Schema creation is non-destructive where expected; PK uniqueness on (date,…) | integration | |

---

## 8. Cross-cutting properties (dedicated regression tests)

1. **No lookahead** — for each point-in-time producer (volatility estimator, feature
   surface, signal engines, returns view), value at `t` is unchanged when input is
   truncated to `< t`. Highest-risk bug class. Tag `@pytest.mark.lookahead`.
2. **Determinism** — identical fixture in → byte-identical backtest out (NAV, trades).
3. **Money invariants** — across any trade sequence: cash ≥ 0 (tolerance), pre-cost NAV
   conserved on a pure rebalance, weights sum to 1.

---

## 9. Out of scope

### Deferred — live / `main.py` path (currently broken)
The live daily-run path is **explicitly not covered** by this suite — it is known
broken and will be addressed separately. No tests target:
- `main.py` (live entry point)
- `src/context/live.py` (`LiveContext`)
- `src/storage/persister.py` (`save_run`, live-only persistence)
- the live wiring of `engine/normalize.normalize_selected_price`, `notify/*`, `visuals/*`

Note: the **backtest** path and all *shared* logic (decision engines, volatility,
covariance, execution, accounting) **are** covered — so most live-path bugs in shared
code will still be caught; only the live entry/context/notification wiring is excluded.

### Low ROI (skip or smoke-only)
- `api_fetch/*` — external (FRED/price APIs). Mock or skip; not in CI.
- `notify/*` — email. Mock the sender; assert payload shape only.
- `visuals/*` — assert "figure builds without error"; no pixel/Streamlit assertions.
- `scenarios/factory.py` — light: builder returns expected config objects.

---

## 10. Suggested phasing
- **Phase 1 (fast wins, no fixtures):** ☑ **DONE** — `backtest/` pure mechanics
  (`test_weights`, `test_valuation`, `test_metrics`, `test_rebalance`) + `strategy/`
  exhaustive decision tables (`test_favourable_assets`, `test_base_allocator`).
  57 tests via `pytest` (config in `pytest.ini`, `pythonpath=.`). Run: `python -m pytest`.
- **Phase 2:** ☑ **DONE** — `tests/conftest.py` (synthetic etf/macro fixtures, signal
  factories, `temp_db`, API-key env stub) → `features/` (`test_volatility_surface`
  ported from the legacy script + `test_covariance`), `data/` (`test_normalize`,
  `test_alignment`, `test_db_reader`), `strategy/` (`test_regime_engine`,
  `test_pipeline_integration`). 40 tests; suite now 97 total. GARCH test marked
  `slow` (deselect with `-m "not slow"`).
- **Phase 3:** ☑ **DONE** — `tearsheets/test_metrics_math` (closed-form), `persistence/test_roundtrip`
  (writers → readers on `temp_db`, incl. NaN→NULL + idempotency), `backtest/test_portfolio`
  (NAV/compounding/weights) and `backtest/test_backtest_e2e` (full deterministic run, marked
  `slow`). 33 tests; suite now 130 passed. Full run ~42s; `-m "not slow"` ~5s.
  - **Bug found & fixed:** `get_backtest_results` selected `gross_notional` but the column is
    `gross_trade_notional` → raised on every call (FE dodged it via `SELECT *`). Fixed in db_reader;
    the persistence round-trip test now exercises the reader directly as a regression guard.
- **Phase 3.5:** ☑ **DONE** — `tearsheets/test_builders` (20 tests): `parse_weights`,
  `build_weight_frame`, `build_exposure_summary` (avg weights match input allocations +
  time-fraction metrics), `merge_regime_trace` + `build_regime_summary` (date/scenario
  alignment, per-regime grouping), `build_benchmark_summary` (output shape + benchmark
  names; strategy≡benchmark → beta/corr = 1). Suite now 150 total (148 + 2 slow).
- **Phase 5 (coverage + gap-fill):** ☑ **DONE** — `pytest-cov` + `.coveragerc` (scope excludes
  external I/O, visuals, and the deferred live path). Added direct tests for the signal engines,
  position-sizer covariance/SHY-buffer + vol scaling, conviction, constraints, legacy allocator,
  scenarios factory, and EWMA covariance. **182 tests; in-scope coverage 82%** (full-tree 71%).
  Run: `python -m pytest --cov=src --cov-report=term-missing`.
  - Remaining in-scope gaps (low value): `execution/rebalance.py` (legacy/unused single-asset path),
    the price-signal wide-format branch, two legacy scenario builders, GARCH error paths, some db writers.
- **Phase 4:** ☑ **DONE** — GitHub Actions CI (`.github/workflows/tests.yml`, Python 3.14,
  runs `pytest` on push to main/dev + PRs), local pre-commit hook (`.pre-commit-config.yaml`,
  fast suite on commit), and `requirements-dev.txt` (pytest + pre-commit). `temp_db` was made
  self-contained (inline schema in conftest) so CI works without the gitignored
  `data/db_population.py`. Enable the hook: `pip install -r requirements-dev.txt && pre-commit install`.

---

## 11. Module → domain coverage matrix
| src module | Domain folder | Priority |
|---|---|---|
| utils/weights.py | backtest | high |
| accounting/valuation.py, metrics.py | backtest | high |
| execution/rebalance_v2.py | backtest | high ⚠️ |
| backtest/portfolio.py, engine.py | backtest | high |
| decision/favourable_asset_selection.py, base_allocator_engine.py | strategy | high |
| decision/regime_engine.py | strategy | high |
| decision/position_sizer_engine.py, constraint_engine.py, constraints.py | strategy | high |
| conviction/engine.py | strategy | med |
| decision/pipeline.py, engine/decision_orchestration.py | strategy | high |
| legacy/legacy_base_weight_allocation.py | strategy | low (frozen) |
| volatility/feature_surface.py, estimator.py, models.py | features | high |
| covariance/estimator.py, returns_view.py | features/data | high |
| signals_price/price_signal_engine.py | strategy/features | med |
| signals_macro/macro_signal_engine.py | strategy/features | med |
| accounting/tearsheet_*.py | tearsheets | med |
| storage/db_reader.py | data/persistence | high |
| storage/db_writer.py | persistence | high |
| engine/normalize.py (normalize_prices), utils/ensure_long.py | data | med |
| api_fetch/*, notify/*, visuals/*, scenarios/* | (skip/smoke) | low |
| **main.py, context/live.py, storage/persister.py** | **(deferred — live path, broken)** | — |
