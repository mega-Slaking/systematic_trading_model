# Design Spec: FastAPI Service + React Analytics Frontend

**Status:** Proposal (no code changes yet — this document only)
**Target version:** see §11 (SemVer)
**Builds on:** the V1.10.0 unified `StrategyConfig` registry (`docs/strategy_config_design_spec.md`, shipped) and the V1.9.5 `EngineContext` Protocol.
**Author:** drafted with quant-engineer analysis
**Date:** 2026-06-10

**Decisions locked (2026-06-10):**
1. **Charting:** Recharts default + Plotly.js (`react-plotly.js`, WebGL) for the dense returns scatter — the split in §7.1. Settled, not an open question. A single-library Plotly-only build was considered and set aside.
2. **Backtest-from-UI:** a planned feature **deferred to post-v1**. v1 is read-only; the job endpoints (§4.3 #13/#14, Phase 5) land in a later version. v1 must preserve the single-writer model so they slot in behind the unchanged 2-endpoint contract; the one prerequisite is making `run_backtest.py:main()` callable as a function.
3. **Deploy target:** **v1 is local-only** (localhost, single analyst). Production-grade hosting — auth, non-`*` CORS, TLS, reverse proxy, durable/restartable jobs — is deferred to a later version (§8, §10).

---

## 1. Executive summary

### Goal
Replace the Streamlit analytics frontend with a **React single-page application (SPA)** served data by a **new FastAPI service**. The FastAPI layer sits *between* the existing Python trading/analytics core and the browser. It **reuses** the existing compute (DB readers, `build_tearsheet`, the backtest engine, the `StrategyConfig` registry) rather than rewriting any of it, and exposes that compute as JSON over REST. Charts that Streamlit currently draws server-side become **data payloads** (series/arrays as JSON) that a client-side React charting library renders.

### Scope (what this migration covers)
The five home-page tabs and the one multi-page view that constitute today's analytics surface:
1. NAV comparison (scenarios vs buy-and-hold benchmarks) + performance summary table.
2. Returns analysis (daily-return scatter by scenario).
3. Tearsheet (per-scenario metrics, equity/drawdown/rolling charts, exposure/regime/benchmark tables) — **the one view with real on-the-fly compute**.
4. ETF prices + price statistics.
5. Volatility features (point-in-time vol surface per asset).
6. Macro indicators vs ETFs (CPI/PMI/yield-curve/fed-funds dual-axis charts).

### Non-goals (explicitly out of scope)
- **No changes to the trading/decision/sizing/execution core.** This is read-only analytics plumbing. The constraint for the *first* implementation phase is the same as this spec: do not modify existing Python compute. (Two small, *optional* hardening fixes are flagged in §10 as future patches, not part of the API work.)
- **No new persisted tables or schema migrations.** The API reads what already exists.
- **No authentication / multi-user / deployment hardening.** Local-dev and single-analyst use. Auth is noted as a future concern (§9).
- **Not resurrecting the deprecated matplotlib `src/visuals/` code** (§2.4) — it is dead and the React app does not depend on it.
- **No live-trading control surface** (kick off trades, change `LIVE_STRATEGY`). Read-only analytics only.

### One-paragraph orientation for the reader
The live analytics frontend is a **Streamlit app built on Plotly (`plotly.graph_objects`) that reads from SQLite** (`data/database.db`). Every dashboard chart is already constructed from explicit `x`/`y` arrays, so this migration is mostly **transport, not a charting rewrite**: (a) re-express each Plotly figure as JSON series the React side draws, and (b) wrap the existing DB reads and the *one* genuine compute path (`build_tearsheet`) behind HTTP. The only real complexity is concentrated in one place — the serialization boundary (§6) — which keeps the project low-risk. (The matplotlib code under `src/visuals/` is deprecated and orphaned — see the §1 non-goal and §2.4 — and plays no part in this migration.)

---

## 2. Current-state analysis

### 2.1 Frontend surface inventory

The Streamlit entry point is `streamlit/app.py`. It renders five tabs from `streamlit/home_page_tabs/`, plus one standalone multi-page view in `streamlit/pages/`. Shared DB loaders live in `streamlit/home_page_tabs/utils.py`.

**Every chart in the live dashboard is already Plotly** (`plotly.graph_objects` / `plotly.subplots`), not matplotlib. That matters: the figures are already constructed from explicit `x`/`y` arrays, so the compute→serialize split for the dashboard is *already done in spirit* — we just move the array construction server-side-of-the-API and the figure construction client-side.

| # | Page / tab | `file:function` | Renders (charts) | Renders (tables / metrics / controls) | Backend it calls |
|---|---|---|---|---|---|
| 1 | NAV Comparison | `streamlit/home_page_tabs/nav_comparison.py:render_nav_comparison_tab` | One multi-line NAV chart: one line per scenario + dashed B&H lines for TLT/AGG/SHY | "Scenario Performance Summary" table: Final NAV, Total Return, Max DD, annualized Vol — **computed inline in the tab** from `nav`/`ret` | `load_backtest_results()`, `load_etf_prices()` |
| 2 | Returns Analysis | `streamlit/home_page_tabs/returns_analysis.py:render_returns_analysis_tab` | Scatter of daily `ret` vs date, one marker series per scenario | none | `load_backtest_results()` |
| 3 | Tearsheet | `streamlit/home_page_tabs/tearsheet.py:render_tearsheet_tab` | Equity curve, drawdown curve, rolling vol + rolling Sharpe (dual-axis) | **~30 `st.metric` tiles** (Total Return, CAGR, Vol, Sharpe, Sortino, Calmar, MaxDD, VaR/CVaR 95, skew, excess kurtosis, avg turnover, worst/best day, parametric VaR, hit rate, payoff, profit factor, avg win/loss); exposure-summary table; regime-summary tables (one per regime type); benchmark-summary table; full summary table; raw scenario-data table. **Control: scenario `selectbox`.** | `load_backtest_results()`, `load_regime_trace()`, `load_etf_prices()`, then **`accounting.tearsheet_builder.build_tearsheet(...)`** (on-the-fly compute) |
| 4 | ETF Prices | `streamlit/home_page_tabs/etf_prices.py:render_etf_prices_tab` | One line per ticker (TLT/AGG/SHY) close price | "Price Statistics" table: first/last/min/max close, total return — computed inline | `load_etf_prices()` |
| 5 | Volatility Features | `streamlit/home_page_tabs/volatility_features.py:render_volatility_features_tab` | Multi-line vol estimates (rolling 20/60, EWMA 0.94/0.97, GARCH) for one selected ticker | "Latest values" table (last row per ticker). **Controls: ticker `selectbox`, methods `multiselect`.** | `load_volatility_features()` |
| 6 | ETFs vs Macro | `streamlit/pages/macro_indicators_vs_etf.py` (module-level script) | Per-ticker ETF-vs-CPI and ETF-vs-PMI dual-axis charts (×3 tickers); 10Y/2Y yield curve + spread; Unemployment vs Sentiment; Fed Funds vs CPI | none (charts only) | inline loaders: `etf_prices`, **raw** `macro_data` (cpi/pmi/gs2/gs10/unemployment/fed_funds/consumer_sentiment), and the **live** `regime_trace` table |

App shell (`streamlit/app.py`): on load it checks the DB exists, calls `load_backtest_results()`, asserts a `scenario_id` column, and shows `len(scenarios)` available scenarios. The React shell must reproduce: a DB/health gate, a scenario list, and a tab router.

> **Inline-compute note:** tabs 1 and 4 compute their summary tables *in the Streamlit layer* (e.g. `nav_comparison.py` annualizes `ret.std()*sqrt(252)`, derives max-DD from `nav.cummax()`). These are not in `tearsheet_calculator`. The API must either (a) reproduce these small reductions server-side, or (b) ship the raw series and let React compute them. This spec recommends (a) — keep all numeric reductions server-side for a single source of truth (§4.2, §7).

### 2.2 Data sources & compute map (cheap query vs. expensive compute)

This is the table that decides **which endpoints are sync vs async** (§5).

| Data the FE needs | Source | `file:function` | Cost class |
|---|---|---|---|
| Backtest daily results (NAV, ret, turnover, costs, weights JSON, n_positions, top_asset/top_weight) | DB `backtest_results` | `streamlit/.../utils.py:load_backtest_results` (`SELECT *`); canonical reader is `src/storage/db_reader.py:get_backtest_results` | **Cheap** (indexed read; ~41k rows total across 10 scenarios in the current DB, ~4k per scenario) |
| Distinct scenario list | DB `backtest_results.scenario_id` | `src/storage/db_reader.py:get_scenario_ids` | **Cheap** (`SELECT DISTINCT`) |
| ETF prices (date,ticker,close) | DB `etf_prices` | `utils.py:load_etf_prices`; `db_reader.py:get_etf_history` | **Cheap** |
| Macro data (cpi/core_cpi/pmi/gs2/gs10/unemployment/payrolls/fed_funds/consumer_sentiment/hy_oas/jobless_claims) | DB `macro_data` | `db_reader.py:get_macro_history`; the macro page uses its own inline `load_macro_data` | **Cheap** |
| Regime trace (inflation/growth/labour/curve_state/macro_supports_duration) | DB `backtest_regime_trace` (scenario-scoped) and live `regime_trace` (page 6) | `utils.py:load_regime_trace`; `db_reader.py:get_backtest_regime_trace` | **Cheap** |
| Volatility feature surface | DB `volatility_features` | `utils.py:load_volatility_features`; `db_reader.py:get_volatility_features` | **Cheap** (pre-built once and persisted; see below) |
| **Tearsheet** (summary metrics + equity/drawdown/rolling curves + exposure/regime/benchmark summaries) | **Computed on the fly** from the three DB reads above | `src/accounting/tearsheet_builder.py:build_tearsheet` → `src/accounting/tearsheet_calculator.py` (Sharpe/Sortino/CAGR/VaR/CVaR/drawdown, rolling 252d, weight parsing, benchmark returns, regime grouping) | **Moderate** (pure pandas/numpy over one scenario's rows; sub-second per scenario — *not* a backtest). Cacheable by `(scenario_id, params)`. |
| **A full backtest run** (produce NAV/weights/trace for the whole registry) | `run_backtest.py:main` → for each `STRATEGIES.values()`: `src/backtest/engine.py:run_backtest` → per-day `src/engine/run.py:run_engine` | builds `CovarianceReturnsView` once, builds the volatility surface once (**~25s with GARCH**, per the subsystem notes), then loops every trading day × every strategy | **Expensive / long-running** (tens of seconds to minutes for the full registry; the dominant one-time cost is the GARCH vol-surface build). This is the only thing that needs an async/job model (§5). |

**Key sizing facts for endpoint design:**
- The dashboard today is *almost entirely* cheap DB reads. Only `build_tearsheet` does real (but fast) compute, and it is trivially cacheable.
- The **expensive** path (a full backtest) is *not currently triggered from the frontend at all* — Streamlit only reads what `run_backtest.py` already persisted. So "run a backtest" is a **new capability**, optional, and the only place an async job queue is justified.
- The volatility surface is **scenario-independent**, built once in `run_backtest.py` and persisted to `volatility_features` (`run_backtest.py:66-83`). The FE reads the persisted table; it never rebuilds the surface.

### 2.3 Entry points: how a backtest is invoked and what it produces

- **Invocation:** `run_backtest.py:main()` (script, no CLI args). It reads history from the DB, computes a `start_date` floor (`max(etf_start, macro_start, 2010-01-01)`), builds the shared `CovarianceReturnsView` and volatility surface once, then iterates `STRATEGIES.values()` (`src/strategy/presets.py`), calling `src/backtest/engine.py:run_backtest(...)` per strategy and tagging every output row with `strategy.name` as `scenario_id`.
- **Config it takes:** a `StrategyConfig` (the V1.10.0 registry object) composing `VolatilityConfig`, `CovarianceConfig`, `PositionSizingConfig`, `ConvictionConfig`, `WeightConstraints`. Initial capital is hardcoded `1_000_000`.
- **In-memory artifacts** (the `BacktestContext`, `src/context/backtest.py`):
  - `context.daily_metrics` — **list of dicts**, one per trading day: `date, nav_pre, nav, ret, turnover, fee_cost, slippage_cost, total_cost, gross_trade_notional, weights (dict), n_positions, top_asset, top_weight`. This is what becomes `backtest_results`.
  - `context.decision_trace`, `context.regime_trace` — lists of dicts → `backtest_decision_trace`, `backtest_regime_trace`.
  - `context.trade_log` — per-trade dicts (date, ticker, side, qty, prices, notionals, costs, reason). **Currently persisted to no table** — available in memory only.
  - The per-day `Decision` dataclass (`src/decision/models.py`) carries far more than is persisted (conviction components, sized vs final weights, vol estimate/target/scale, notes). Only a projection reaches the DB.
- **Output form:** persisted via `src/storage/db_writer.py` (`insert_backtest_results`, `insert_backtest_decision_trace`, `insert_backtest_regime_trace`, `insert_volatility_features`) into SQLite at `src/storage/paths.py:DB_PATH` (`data/database.db`).

**Implication for the API:** every artifact the dashboard shows is a **DataFrame or a list-of-dicts or a dataclass** — all of which serialize cleanly to JSON (§6). The frontend never touches an in-memory engine object directly; it goes through the DB or `build_tearsheet`. This is exactly the seam FastAPI slots into.

### 2.4 Coupling: where plotting meets computation

The finding is favorable — compute and rendering are already well separated.

1. **`src/visuals/` (matplotlib) is deprecated and orphaned — leave it untouched.** `backtest_analysis.py`, `plots.py`, `visualizer.py` are pure matplotlib; `visualizer.py:generate_daily_report` is marked *"DEPRECATED: no longer wired into the live run"* and its only call site (`src/context/live.py:visualize`) is a no-op (`pass # disabled`), as is `BacktestContext.visualize`. No Streamlit file imports `src/visuals/`. Decision: leave it in place (repo convention: don't delete) — it plays no role in this migration.

2. **The Streamlit Plotly tabs mix compute + draw, but the compute is trivial and the data is already array-shaped.** Each `render_*_tab` does `load → (small reduction) → go.Figure(...) → st.plotly_chart`. The "entanglement" is: the figure object is built in the same function as the data. The clean split is mechanical because the inputs to `go.Scatter` are already `x=df["date"], y=df["nav"]`. Server-side, the endpoint returns those two arrays; client-side, React feeds them to the chart. **No numeric logic is trapped inside a matplotlib/plotly call** anywhere in the dashboard.

3. **`build_tearsheet` is already cleanly separated (compute-only).** `tearsheet_builder.py` / `tearsheet_calculator.py` return a `TearsheetResult` dataclass of DataFrames + a `TearsheetMetrics` dataclass of floats. **It draws nothing.** The Streamlit tab does all plotting from the returned DataFrames. This is the ideal shape for an API: call `build_tearsheet`, serialize the dataclass. **No decoupling work needed.**

4. **The only genuine entanglement to undo is the inline reductions in tabs 1 & 4** (NAV summary stats; price statistics) — they live in the Streamlit layer, not in a reusable module. The API must reimplement these few lines server-side (≈15 lines total) so React doesn't have to. Small, contained, and they belong server-side anyway.

**Net coupling risk: LOW.** The architecture already separates compute (DB readers + `build_tearsheet`) from rendering (Plotly in Streamlit). The migration is mostly transport, not surgery.

### 2.5 Confirmed schema/contract issues surfaced during investigation

These are *not* introduced by this spec; they exist today and the API must be designed to dodge them (and they motivate the optional hardening in §10).

- **Column-name drift (`gross_trade_notional` vs `gross_notional`).** The DB column, writer (`db_writer.py:insert_backtest_results`), and reader (`db_reader.py:get_backtest_results`) all use **`gross_trade_notional`**. But the Tearsheet raw-data table (`tearsheet.py:_display_raw_data`) lists `"gross_notional"` in its display columns — which simply never matches, so that column is silently dropped from the raw table. This is the same class of reader/writer drift the README calls out as deferred item 8. The API's response model must standardize on **`gross_trade_notional`** (the persisted truth) and not propagate the typo.
- **Two readers for `backtest_results` disagree on shape.** `utils.py:load_backtest_results` does `SELECT *` (returns whatever columns exist, including `gross_trade_notional`); `db_reader.py:get_backtest_results` enumerates an explicit column list. The API should use the **explicit reader** (`db_reader.py`) as the canonical source, not `SELECT *`, so the JSON contract is stable regardless of stray columns.
- **`config_key` semantics on `volatility_features`.** The writer stores `config_key = str(config.cache_key())` and the surface is scenario-independent (one row per `(date,ticker)`); the API should treat `config_key` as opaque metadata, not a filter the FE exposes.

### 2.6 Data readiness (verified against `data/database.db`, 2026-06-10)

The live DB is present (24 MB) and **every table the API needs is populated** — no `db_population.py` / `run_backtest.py` re-run is required before building:

| Table | Rows | Range | Note |
|---|---|---|---|
| `backtest_results` | 41,310 | 2010-01-05 → 2026-06-08 | 10 scenarios (the `baseV1_*` grid + `default`) |
| `etf_prices` | 17,718 | 2002-07-30 → 2026-06-09 | tickers TLT/AGG/SHY |
| `macro_data` | 294 | 2002-01-01 → 2026-06-01 | **monthly** cadence (see below) |
| `backtest_regime_trace` | 41,310 | 2010-01-05 → 2026-06-08 | scenario-scoped |
| `volatility_features` | 18,009 | 2002-07-30 → 2026-06-08 | TLT/AGG/SHY — surface already built |
| `regime_trace` (live) | **10** | 2026-04-24 → 2026-06-10 | **sparse** (see below) |

Three readiness notes for the build:
- **Live `regime_trace` is tiny (10 rows, ~6 weeks).** Page 6 consumes the *live* table, so its regime overlay will be minimal until live trading accrues more history. Not a bug — design the Macro page to render gracefully with a near-empty regime series.
- **`macro_data` is monthly while `etf_prices`/`backtest_results` are daily.** The dual-axis macro-vs-ETF charts mix cadences; plot each series on its own date axis (as Streamlit does) — do **not** assume a shared/aligned daily index when merging.
- **Bonus:** `backtest_decision_trace` is also populated (41,310 rows), so the deferred "richer per-day `Decision` fields" endpoint (§12) is **data-feasible without schema work** if ever wanted — the data already persists; only an endpoint is missing.

---

## 3. Target architecture

### 3.1 Layering (how the API reuses, not rewrites, the core)

```
┌──────────────────────────────────────────────────────────────┐
│  React SPA (Vite + TypeScript)                                │
│   - pages mirror the 6 Streamlit views (§7)                   │
│   - charting library renders JSON series client-side          │
│   - fetches via a typed api/ client (TanStack Query)          │
└───────────────▲──────────────────────────────────────────────┘
                │  HTTP/JSON (REST), CORS-enabled
┌───────────────┴──────────────────────────────────────────────┐
│  FastAPI service  (NEW — lives in api/)                       │
│   routers/      thin HTTP layer: path, params, status codes   │
│   schemas/      Pydantic response/request models (the contract)│
│   services/     orchestration: call core, shape into schemas  │
│   serialization/ DataFrame/Series/dataclass -> JSON helpers   │
│   (NO trading/analytics logic re-implemented here)            │
└───────────────▲──────────────────────────────────────────────┘
                │  in-process Python imports (no new compute)
┌───────────────┴──────────────────────────────────────────────┐
│  EXISTING Python core (unchanged)                             │
│   src/storage/db_reader.py      cheap DB reads                │
│   src/accounting/tearsheet_*    build_tearsheet (compute)     │
│   src/backtest/engine.py        run_backtest (long-running)   │
│   src/strategy/presets.py       STRATEGIES registry           │
│   src/storage/paths.py          DB_PATH (single source)       │
└──────────────────────────────────────────────────────────────┘
```

**Design rule:** routers and services may *import and call* `src/...` but must **not** contain analytics math. Anything numeric that doesn't already exist in `src/` (the inline NAV/price summaries from §2.4.4) goes into a thin `api/services/summaries.py` helper module — additive, not a change to existing code. This preserves "the FastAPI layer reuses the compute."

### 3.2 Proposed backend directory structure

A new top-level `api/` package (sibling to `src/`, `streamlit/`), keeping the API distinct from the engine just as `streamlit/` is today:

```
api/
  __init__.py
  main.py                  # FastAPI() app, CORS, router registration, /health
  config.py                # API settings (host/port/CORS origins/cache TTLs) via pydantic-settings
  deps.py                  # shared dependencies (DB path, cache handle)
  routers/
    __init__.py
    scenarios.py           # GET /scenarios, /scenarios/{id}/...
    backtest_results.py    # GET /backtest-results (daily rows, NAV series, returns)
    tearsheet.py           # GET /tearsheet/{scenario_id}
    etf_prices.py          # GET /etf-prices (+ stats)
    macro.py               # GET /macro, /macro/yield-curve
    volatility.py          # GET /volatility-features
    strategies.py          # GET /strategies (registry introspection)
    jobs.py                # POST /jobs/backtest, GET /jobs/{id}  (optional, §5)
  schemas/
    __init__.py
    common.py              # SeriesPoint, NamedSeries, TableModel, error envelope
    backtest.py            # NavComparisonResponse, BacktestDailyRow, ...
    tearsheet.py           # TearsheetResponse mirroring TearsheetResult/Metrics
    etf.py                 # EtfPriceSeries, PriceStat
    macro.py               # MacroSeries, YieldCurveResponse
    volatility.py          # VolFeatureSeries, VolLatestRow
    strategy.py            # StrategySummary
    jobs.py                # JobStatus
  services/
    __init__.py
    backtest_results.py    # wraps db_reader + NAV/B&H/summary shaping
    tearsheet.py           # wraps build_tearsheet, serializes TearsheetResult
    etf_prices.py          # wraps get_etf_history + price stats
    macro.py               # wraps get_macro_history + derived spread
    volatility.py          # wraps get_volatility_features + latest-per-ticker
    strategies.py          # introspect STRATEGIES into JSON
    summaries.py           # the §2.4.4 inline reductions, server-side, ONE home
    jobs.py                # background backtest orchestration (optional, §5)
  serialization/
    __init__.py
    frames.py              # df_to_records / series_to_points / nan->null / date->ISO
    dataclasses.py         # tearsheet dataclass -> dict with frame fields expanded
  cache.py                 # tiny in-process TTL/LRU cache (§5.2)
  tests/
    test_health.py
    test_scenarios.py
    test_tearsheet_endpoint.py
    test_serialization.py  # NaN/date/precision round-trips

frontend/                  # React SPA (Vite); see §7 for internal structure
```

`requirements.txt` gains `fastapi`, `uvicorn[standard]`, `pydantic-settings` (pydantic v2), and optionally `orjson` (perf only — see the §8 toolchain note on Python 3.14 wheels). API test deps (`httpx` for FastAPI's `TestClient`) go in `requirements-dev.txt`. No change to the existing `src/` tree.

### 3.3 How the API process talks to the engine

In-process imports, same interpreter — the API is a thin Python host around `src/`. There is **no** subprocess or RPC to the engine for the read paths. The DB is opened read-only per request (SQLite, short-lived connections, exactly as the readers already do via `_connect()`). For the optional long-running backtest job (§5), the work runs in a background worker *inside* the same app (or a separate process reading/writing the same `data/database.db`).

**Import-root caveat (verified 2026-06-10).** The existing core mixes import roots: `src/storage/db_reader.py` does `from src.storage.paths import ...` (needs the **repo root** on `sys.path`), while `src/accounting/tearsheet_builder.py` does `from accounting.tearsheet_models import ...` (needs **`src/`** on `sys.path`, since `accounting` lives at `src/accounting`). The API process must put **both** the repo root *and* `src/` on `sys.path` at startup, or imports fail — replicate whatever the existing Streamlit/test harness does (`api/main.py` or `api/config.py` inserting both paths; launch uvicorn from the repo root). This is a startup prerequisite, not a runtime concern.

---

## 4. API design

### 4.1 Conventions

- Base path `/api/v1`. JSON only. `snake_case` field names (matches the Python/DB vocabulary the analyst already knows; the React client maps to camelCase at its boundary if desired).
- Dates serialized as **ISO-8601 `YYYY-MM-DD`** strings (the data is daily; no intraday component). NaN/Inf serialized as JSON `null` (§6).
- Money as plain `float` (NAV in dollars); ratios/returns as decimal fractions (e.g. `0.0123` = 1.23%) — **formatting is the React layer's job**, the API never returns pre-formatted `"1.23%"` strings (Streamlit did this in-tab; we deliberately move it client-side so values stay machine-usable).
- Errors use a consistent envelope: `{ "detail": "...", "code": "SCENARIO_NOT_FOUND" }` with appropriate HTTP status (404 unknown scenario, 422 bad params, 503 DB missing).

### 4.2 Core shared schemas (`api/schemas/common.py`)

The figure-to-payload strategy hinges on two primitives. A Plotly/matplotlib trace is just *(name, x[], y[])* — we ship exactly that and let React draw it.

```python
from pydantic import BaseModel

class SeriesPoint(BaseModel):
    date: str           # "YYYY-MM-DD"
    value: float | None # NaN -> null

class NamedSeries(BaseModel):
    name: str                  # trace/legend label, e.g. "B&H: TLT" or "rolling_sharpe"
    points: list[SeriesPoint]  # the (x,y) the chart library plots
    meta: dict | None = None   # optional: {"dash": "dash"} style hints, units, axis id

class TableModel(BaseModel):
    columns: list[str]
    rows: list[dict]           # list-of-records; values are JSON scalars or null
```

> **Why `list[SeriesPoint]` and not parallel `x[]/y[]` arrays?** Slightly more verbose on the wire but null-safe per point and trivial to map in React (`data.map(p => ({x: p.date, y: p.value}))`). For very large multi-scenario payloads (returns scatter) an optional columnar form `{ "dates": [...], "values": [...] }` is allowed — see §4.4 endpoint note and §10 (payload size).

### 4.3 Endpoint catalog

Twelve read endpoints across six routers, plus one health probe and the optional two-endpoint job pair (a **13–15 endpoint** surface depending on whether the backtest-trigger is built). Each maps directly to a Streamlit view from §2.1.

| # | Method & path | Purpose / FE view | Query / body | Cost |
|---|---|---|---|---|
| 0 | `GET /api/v1/health` | DB-exists gate (replaces `app.py` `DB_PATH.exists()` check) | — | trivial |
| 1 | `GET /api/v1/scenarios` | Scenario picker + count (app shell) | — | cheap |
| 2 | `GET /api/v1/backtest-results/nav-comparison` | **Tab 1** NAV chart + summary table | `scenario_ids?` (default all), `benchmarks?=TLT,AGG,SHY` | cheap |
| 3 | `GET /api/v1/backtest-results/returns` | **Tab 2** daily-return scatter | `scenario_ids?` | cheap |
| 4 | `GET /api/v1/backtest-results/{scenario_id}/daily` | **Tab 3** raw scenario table | `columns?`, `limit?/offset?` | cheap |
| 5 | `GET /api/v1/tearsheet/{scenario_id}` | **Tab 3** full tearsheet | `risk_free_rate?=0.02`, `periods_per_year?=252` | moderate (cached) |
| 6 | `GET /api/v1/etf-prices` | **Tab 4** price lines | `tickers?=TLT,AGG,SHY` | cheap |
| 7 | `GET /api/v1/etf-prices/stats` | **Tab 4** price statistics table | `tickers?` | cheap |
| 8 | `GET /api/v1/volatility-features` | **Tab 5** vol surface lines | `ticker` (required), `methods?` | cheap |
| 9 | `GET /api/v1/volatility-features/latest` | **Tab 5** latest-per-ticker table | — | cheap |
| 10 | `GET /api/v1/macro` | **Page 6** macro series for dual-axis charts | `indicators?=cpi,pmi,fed_funds,...` | cheap |
| 11 | `GET /api/v1/macro/yield-curve` | **Page 6** 10Y/2Y + spread | — | cheap |
| 12 | `GET /api/v1/strategies` | Registry introspection (new capability) | — | cheap |
| 13* | `POST /api/v1/jobs/backtest` | **Optional** trigger a registry backtest | body `{ strategy_names?: [...] }` | long-running |
| 14* | `GET /api/v1/jobs/{job_id}` | **Optional** poll job status/result location | — | cheap |

`*` = optional, gated on whether "run a backtest from the UI" is wanted (§5). The read-only dashboard (endpoints 0–12) is fully functional without them.

### 4.4 Representative response schemas

**Endpoint 2 — NAV comparison (Tab 1).** Bundles the scenario lines, the benchmark lines, and the inline-computed summary (moved server-side per §2.4.4):

```python
# api/schemas/backtest.py
class ScenarioSummaryRow(BaseModel):
    scenario_id: str
    final_nav: float
    total_return: float        # decimal fraction
    max_drawdown: float
    annualized_volatility: float | None  # None if 'ret' absent

class NavComparisonResponse(BaseModel):
    start_date: str
    initial_nav: float
    scenario_series: list[NamedSeries]   # one per scenario ("Scenario: <id>")
    benchmark_series: list[NamedSeries]  # dashed B&H lines, meta={"dash":"dash"}
    summary: list[ScenarioSummaryRow]
```
Service: `services/backtest_results.py` calls `db_reader.get_backtest_results()` (canonical reader, **not** `SELECT *`), reuses the benchmark math currently inline in `nav_comparison.py` (B&H NAV = `initial_nav * close/first_close`, windowed to `results["date"].min()`), and the summary reductions go through `services/summaries.py`.

**Endpoint 3 — returns scatter (Tab 2).** Potentially the largest payload (every day × every scenario). Use the columnar variant to cut JSON size:

```python
class ReturnsScatterSeries(BaseModel):
    scenario_id: str
    dates: list[str]
    returns: list[float | None]

class ReturnsResponse(BaseModel):
    series: list[ReturnsScatterSeries]
```

**Endpoint 5 — tearsheet (Tab 3).** A faithful 1:1 serialization of `TearsheetResult` + `TearsheetMetrics` (`src/accounting/tearsheet_models.py`). The DataFrames become `NamedSeries` (curves) or `TableModel` (summaries); the metrics dataclass becomes a flat object:

```python
# api/schemas/tearsheet.py
class TearsheetMetricsModel(BaseModel):
    scenario_id: str
    start_date: str
    end_date: str
    total_return: float; cagr: float; annualized_volatility: float
    sharpe: float; sortino: float; max_drawdown: float; calmar: float
    var_95: float; cvar_95: float; worst_day: float; best_day: float
    skew: float; excess_kurtosis: float
    avg_turnover: float; annualized_turnover: float
    total_cost: float; cost_drag: float | None
    daily_hit_rate: float; avg_win: float; avg_loss: float
    payoff_ratio: float; profit_factor: float; parametric_var_95: float

class TearsheetResponse(BaseModel):
    summary: TearsheetMetricsModel
    equity_curve: NamedSeries          # from TearsheetResult.equity_curve (date,nav)
    drawdown_curve: NamedSeries        # (date,drawdown)
    rolling_metrics: list[NamedSeries] # rolling_volatility, rolling_sharpe (+ rolling_return)
    exposure_summary: TableModel | None
    regime_summary: TableModel | None  # includes regime_type column; React groups
    benchmark_summary: TableModel | None
    regime_match_rate: float | None    # the caption Streamlit shows
```
Service: `services/tearsheet.py` loads the same three frames the tab loads (`get_backtest_results(scenario_id)`, `get_backtest_regime_trace(scenario_id)`, `get_etf_history()`), calls **`build_tearsheet(...)` unchanged**, then walks the result via `serialization/dataclasses.py`. `regime_match_rate` reproduces the tab's debug caption (`merged["inflation_regime"].notna().mean()`). **Zero new analytics.** *(Verified 2026-06-10: `TearsheetMetricsModel` above is a field-for-field match of the real `TearsheetMetrics` dataclass — all 26 fields, `cost_drag` the only nullable. `build_tearsheet(results_df, regime_df, benchmark_prices_df, risk_free_rate=0.02, periods_per_year=252)` matches endpoint 5's params and the three-frame load. It raises `ValueError` on empty input, on missing `{date, scenario_id, nav}`, and on >1 `scenario_id` — caught and mapped per §10.9.)*

**Endpoint 8 — volatility features (Tab 5).** One series per requested method for one ticker; method allow-list mirrors the tab's `_VOL_METHODS` keys:

```python
class VolatilityFeaturesResponse(BaseModel):
    ticker: str
    series: list[NamedSeries]          # rolling_20, rolling_60, ewma_94, ewma_97, garch
    available_methods: list[str]       # which columns are non-empty for this ticker
```

**Endpoint 11 — yield curve (Page 6).** Server computes the spread (`gs10 - gs2`) that the page currently computes inline:

```python
class YieldCurveResponse(BaseModel):
    gs10: NamedSeries
    gs2: NamedSeries
    spread: NamedSeries                # gs10 - gs2, meta={"fill":"tozeroy"}
```

**Endpoint 12 — strategies (new).** Introspects the registry so the UI can show what each `scenario_id` *means* (today the dashboard shows opaque names like `baseV1_roll20_ewmacov_lam94_tv05`):

```python
class StrategySummary(BaseModel):
    name: str
    description: str | None
    starting_weight_source: str        # "conviction" | "legacy"
    use_vol_scaling: bool
    vol_scaling_power: float
    use_covariance_scaling: bool
    target_portfolio_vol: float
    cov_method: str
    is_live: bool                      # name == presets.LIVE_STRATEGY
```
Service flattens `STRATEGIES` (`src/strategy/presets.py`) by reading each `StrategyConfig`'s nested sub-configs. Read-only introspection; it does not let the UI *change* the live strategy.

### 4.5 matplotlib/PNG-bytes fallback (interim option)

The recommended design ships **data, not images** for every chart (all six views are line/scatter charts that a JS library draws natively). However, an image-bytes endpoint is a pragmatic fallback worth keeping in the back pocket for two narrow cases:
- If a *future* analytic produces a chart type that's painful in JS (e.g. a dense heatmap of the covariance matrix, or a regime "phase ribbon" like the deprecated `plot_inflation_regime`), a `GET /api/v1/figures/{name}.png` returning `image/png` (rendered via the existing matplotlib helpers with `Agg` backend, `StreamingResponse`) is a legitimate stopgap.
- For a "download this chart" export feature.

This is explicitly **not** part of the core migration — the dashboard parity target uses JSON series end-to-end. If the PNG route is ever added, it must use a headless `matplotlib.use("Agg")` backend and must not become the primary render path (it defeats interactivity, theming, and client-side zoom).

---

## 5. Long-running compute & caching

### 5.1 Sync vs background vs job-queue — recommendation

Decision driver (§2.2): **only the full backtest is long-running, and it is currently a new capability, not something the dashboard does.** Everything the existing dashboard needs is cheap-read or fast-compute. So:

| Workload | Latency | Model | Rationale |
|---|---|---|---|
| All DB-read endpoints (2,3,4,6–12) | ms | **Synchronous** | Cheaper than the HTTP overhead; no async machinery warranted. |
| Tearsheet (5) | sub-second/scenario | **Synchronous + cache** | Fast pandas; caching makes repeat scenario-switching instant. Run in a threadpool (`def` endpoint, FastAPI offloads sync work) so a slow scenario can't block the event loop. |
| Full backtest (13/14, optional) | tens of s – minutes | **Background task + polling** | The GARCH surface build alone is ~25s; the registry loop adds more. Must not block a request. |

**Recommended job model for the optional backtest trigger: FastAPI `BackgroundTasks` + an in-process job registry with status polling — NOT a full Celery/RQ/broker stack.** Rationale:
- This is a **single-analyst, single-node** tool (the same machine runs `run_backtest.py` today). A Redis/Celery deployment is operational overkill for one user kicking off an occasional backtest.
- Pattern: `POST /jobs/backtest` validates `strategy_names` (subset of `STRATEGIES`), creates a `job_id`, launches the work via `BackgroundTasks` (or a bounded `concurrent.futures` worker so only one backtest runs at a time — the engine writes to one SQLite file), and returns `202 Accepted` with `{ job_id, status: "queued" }`. The worker calls the **existing** `run_backtest.py` logic (refactored only insofar as wrapping `main()`'s body in a callable — that refactor is *future work*, not this spec's no-edit phase). `GET /jobs/{job_id}` returns `{ status: queued|running|done|error, started_at, finished_at, scenario_ids_written, detail }`.
- **Concurrency guard:** serialize backtests (a simple lock / single-slot executor). Two concurrent runs writing `INSERT OR REPLACE` into the same `data/database.db` would race; SQLite + one writer is the safe model. Reads can proceed concurrently (WAL mode optional).
- **Upgrade path:** if this ever becomes multi-user or needs durable/restartable jobs, swap the in-process registry for RQ/Celery + Redis behind the same two-endpoint contract. The API surface doesn't change.

**Decision: endpoints 13/14 are deferred to post-v1** (planned, not cut). v1 ships read-only — the analyst keeps running `python run_backtest.py` from the shell and the SPA visualizes the persisted results (full parity with today's Streamlit, which also can't trigger a run). v1 keeps the single-writer model so the job feature bolts on later behind the unchanged 2-endpoint contract; the one prerequisite is making `run_backtest.py:main()` callable as a function (a small future refactor, not part of v1).

### 5.2 Caching strategy

- **Tearsheet cache (the high-value one):** key on `(scenario_id, risk_free_rate, periods_per_year)`. The underlying `backtest_results` for a scenario is immutable until the next `run_backtest`, so cache entries are valid until a new backtest writes. A small in-process **LRU/TTL dict** (`api/cache.py`) suffices; TTL ~ a few minutes plus an explicit invalidation hook the (optional) job worker calls on completion. Mirrors what Streamlit got "for free" from `@st.cache_data`.
- **DB-read endpoints:** cache lightly (short TTL, e.g. 30–60s) keyed on the query params. These reads are already fast; caching mostly smooths repeated tab switches. The big `SELECT *` scenario table benefits most.
- **Cache invalidation = backtest completion.** The only thing that mutates analytics data is a backtest writing the DB. Whether triggered via endpoint 13 or the CLI, expose a manual `POST /api/v1/cache/flush` (or fold invalidation into the job worker) so a fresh run is reflected without restarting the API. (For CLI-triggered runs with no job hook, the short TTLs ensure eventual freshness; a manual flush makes it immediate.)
- **HTTP caching:** set `Cache-Control` / `ETag` on read responses keyed off the DB file mtime + params, letting the browser and TanStack Query skip refetches. Cheap win, no server state.

---

## 6. Serialization strategy

The whole core speaks **DataFrame / Series / dataclass / dict** (§2.3). One small `api/serialization/` module centralizes the conversion so every endpoint is consistent. The hazards are the classic three: dates, NaN/Inf, and float precision.

- **Dates.** Inputs are pandas `Timestamp` (readers `parse_dates=["date"]`) or `date` strings. Normalize **everything** to ISO `YYYY-MM-DD` via a single helper. The data is daily — drop any time component. `frames.py:to_iso(series)` → `series.dt.strftime("%Y-%m-%d")`. **Confirmed 2026-06-10:** the DB is genuinely inconsistent here — `backtest_results.date` is stored *with* a `00:00:00` time component, while `etf_prices`/`macro_data`/`volatility_features`/`regime_trace` store plain `YYYY-MM-DD`. This is exactly why every date must pass through the one normalizer; never hand a raw DB date string to the client.
- **NaN / Inf → `null`.** This is the sharp edge. `tearsheet_calculator` deliberately returns `np.nan` for undefined stats (empty tails, zero-variance benchmarks → `safe_divide`), and rolling metrics are NaN for the first 252 rows. **JSON has no NaN**; `json.dumps(float("nan"))` emits invalid `NaN` tokens that break strict parsers. Mitigation: a single sanitizer `nan_to_none(x)` applied to every float at the serialization boundary (`x if isinstance(x,float) and x==x and not isinf(x) else None`), and configure FastAPI/Pydantic to emit `null` (Pydantic v2 with `float | None` fields + a model-level serializer, or `ORJSONResponse` with a NaN-handling default). The writer already has the exact idiom to copy (`db_writer.py:_none_if_nan`). React renders `null` as a gap in the line — correct behavior for "metric not defined yet."
- **DataFrame → records / series.** Two converters: `df_to_table(df) -> TableModel` (generic table: `{columns, rows}` via `df.where(pd.notna, None).to_dict("records")`) and `df_to_series(df, x="date", y=col, name=...) -> NamedSeries`. The tearsheet `regime_summary` (variable columns by regime type) and `benchmark_summary` go through `df_to_table`; the curves go through `df_to_series`.
- **Dataclass → dict.** `TearsheetMetrics` is a frozen dataclass of plain floats/strs → `dataclasses.asdict` then NaN-sanitize. `TearsheetResult` mixes a dataclass with DataFrame fields → a bespoke walker (`serialization/dataclasses.py`) that maps each known field to the right converter. (Streamlit already does `asdict(summary)` in `_display_summary_table`, confirming this is straightforward.)
  - **Verified 2026-06-10 (column contract for the walker):** `equity_curve` → cols `(date, nav)`; `drawdown_curve` → `(date, drawdown)`; `rolling_metrics` → a *single* DataFrame with cols `(date, rolling_return, rolling_volatility, rolling_sharpe)` that the walker **splits into three `NamedSeries`**. `regime_match_rate` is **not** a dataclass field — the service computes it (`merged["inflation_regime"].notna().mean()`), so it is additive, not a serialization of `TearsheetResult`.
  - **Empty-vs-None gotcha (verified 2026-06-10):** `exposure_summary`/`regime_summary`/`benchmark_summary` are annotated `pd.DataFrame | None`, but the builders actually return an **empty `pd.DataFrame()`** (not `None`) on their no-data paths. The walker must branch on **`df.empty`**, not `is None`, to emit `null`/empty-table — checking `is None` alone would let an empty frame through as a `{columns:[],rows:[]}` table or crash a `df_to_series` call.
- **Float precision.** NAV values are large dollars; returns are tiny decimals. Don't pre-round server-side (keep full float64 precision; let React format for display). The only rounding consideration is wire size for the big returns scatter — optionally round returns to ~8 dp there (negligible visual loss, smaller payload). Use `orjson` (via `ORJSONResponse`) for fast, correct float serialization.
- **`weights` column.** `backtest_results.weights` is stored as a JSON string (writer `_json_if_dict`). The daily-rows endpoint should parse it back to an object so React gets `{"TLT":0.1,...}` not a string — reuse `tearsheet_calculator.parse_weights` (already handles JSON/`ast`/NaN) so the API doesn't reinvent it.

---

## 7. React frontend architecture

### 7.1 Charting library recommendation

**Decision (locked): Recharts** as the default, with **Plotly.js (`react-plotly.js`, WebGL `scattergl`) for the dense returns scatter** — and as a drop-in escape hatch for any other view that wants Plotly's richer interactions.

Trade-offs considered:

| Library | Pros | Cons | Fit here |
|---|---|---|---|
| **Recharts** (recommended) | Declarative React-native API, small, easy theming, perfect for the line/scatter/dual-axis charts that are 100% of this dashboard; great DX for `<LineChart><Line dataKey=.../></LineChart>` | Struggles with very dense scatter (the returns plot's tens of thousands of points) and exotic chart types | Covers tabs 1,3,4,5,6 cleanly; dual-axis (rolling vol/Sharpe, ETF-vs-macro) is first-class |
| **Plotly.js / react-plotly.js** | **Zero conceptual port** — the Streamlit charts are *already Plotly*; same `go.Scatter`-style traces, built-in zoom/pan/hover/unified-hover (which the tabs already use), WebGL `scattergl` handles the dense returns scatter | Heavier bundle (~3MB), imperative figure objects feel un-React-y | Ideal for the **returns scatter** (tab 2, WebGL) and as a literal 1:1 of existing figures; pragmatic for a fast first slice |
| ECharts (echarts-for-react) | Very capable, performant, canvas-based | Larger API surface to learn; less idiomatic in React | Overkill for this chart set |
| Visx / D3 | Maximum control | Build-it-yourself axes/tooltips; slowest to ship | Not justified |

**Why this split:** Recharts gives the cleanest long-term React codebase for the common case, but because the existing charts are Plotly, `react-plotly.js` lets the **first vertical slice ship almost verbatim** (translate the `go.Figure` to a Plotly JSON spec) and decisively solves the one performance worry (dense returns scatter via `scattergl`). Concretely: build everything in Recharts **except** the returns scatter (tab 2), which uses Plotly WebGL. (A single-library Plotly-everything build was considered and set aside in favor of the split — it accepts Plotly's ~3MB bundle only where WebGL is actually needed.)

### 7.2 Component structure (mapped to the page inventory)

```
frontend/
  src/
    main.tsx                 # app bootstrap, QueryClientProvider, router
    App.tsx                  # shell: header, scenario context, tab nav (mirrors streamlit/app.py)
    api/
      client.ts              # fetch wrapper, base URL from env, error envelope handling
      types.ts               # TS types mirroring api/schemas (generate from OpenAPI, §7.4)
      hooks.ts               # useScenarios(), useTearsheet(id), useNavComparison(), ...
    components/
      charts/
        SeriesLineChart.tsx  # NamedSeries[] -> Recharts line chart (shared by most tabs)
        DualAxisChart.tsx    # two NamedSeries on secondary y-axis (rolling, ETF-vs-macro)
        ReturnsScatter.tsx   # Plotly scattergl for the dense returns plot
      tables/
        DataTable.tsx        # TableModel -> sortable table (exposure/regime/benchmark/raw)
        MetricGrid.tsx       # the ~30 tearsheet metric tiles (st.metric equivalent)
      ScenarioSelect.tsx     # dropdown (tearsheet + global filter)
      HealthGate.tsx         # blocks app if /health says no DB (replaces app.py guard)
    pages/
      NavComparisonPage.tsx  # tab 1  -> SeriesLineChart + summary DataTable
      ReturnsPage.tsx        # tab 2  -> ReturnsScatter
      TearsheetPage.tsx      # tab 3  -> MetricGrid + equity/dd/rolling charts + tables
      EtfPricesPage.tsx      # tab 4  -> SeriesLineChart + stats DataTable
      VolatilityPage.tsx     # tab 5  -> SeriesLineChart + method multiselect + latest table
      MacroPage.tsx          # page 6 -> DualAxisChart grid + yield-curve chart
    lib/
      format.ts              # percent/currency/ratio formatters (the "%.2%"/"$,.0f" logic
                             #   Streamlit did inline now lives here, client-side)
    theme.ts                 # colors, matches the plotly_white look
```

Each `pages/*` component is a near-mechanical translation of one `render_*_tab`: same controls (now React state), same chart(s) (now `NamedSeries`-driven), same tables (now `TableModel`-driven). The **formatting** that Streamlit did inline (`f"{x:.2%}"`, `f"${x:,.0f}"`) moves into `lib/format.ts` — the API returns raw numbers (§4.1).

### 7.3 State & data-fetching

**Recommendation: TanStack Query (React Query) over a thin `fetch` client.** Rationale:
- The app is **read-mostly server state**, which is exactly TanStack Query's sweet spot: caching, dedupe, background refetch, stale-while-revalidate, loading/error states per query. It replicates `@st.cache_data` on the client and pairs with the server `ETag`/`Cache-Control` from §5.2.
- No need for Redux/global mutable state — the only "global" UI state is the selected scenario(s) and the active tab, which live in URL/route + a small React context.
- Query keys mirror endpoints: `["tearsheet", scenarioId, rfr, ppy]`, `["nav-comparison", scenarioIds]`, etc. — invalidate the lot on a backtest-complete event (if the job feature exists).
- For the optional backtest job: `useMutation` to `POST /jobs/backtest`, then poll `GET /jobs/{id}` with `refetchInterval` until `done`, then invalidate analytics queries.

### 7.4 Type safety across the boundary

FastAPI auto-generates an **OpenAPI schema** from the Pydantic models. Generate the TS `api/types.ts` from it (`openapi-typescript`) so the React types are derived from the Python contract — drift becomes a compile error, echoing how the repo already enforces the `EngineContext` contract with pyright. This is the frontend analogue of the project's "validate the contract" discipline.

---

## 8. Cross-cutting concerns

- **CORS.** Vite dev server (default `http://localhost:5173`) and the FastAPI server (suggest `http://localhost:8000`) are different origins → `CORSMiddleware` with an allow-list from `api/config.py` (dev: localhost:5173; prod: the served SPA origin). Alternatively, Vite's dev proxy forwards `/api` to `:8000`, sidestepping CORS in dev — recommend the proxy for local DX and keep `CORSMiddleware` for safety/prod.
- **Config & secrets.** The analytics API is **read-only over SQLite and needs no secrets** — crucially, it does **not** import `config.py`/`FRED_API_KEY` or any fetch path (those are for `run_backtest`/live ingestion, not analytics). API settings (host, port, CORS origins, cache TTLs, `DB_PATH` override) via `pydantic-settings` reading env/`.env`, consistent with the repo's existing `python-dotenv` use. Reuse `src/storage/paths.py:DB_PATH` as the default so the API and engine agree on the DB location by construction.
- **Error handling.** A FastAPI exception handler maps domain errors to the §4.1 envelope: unknown `scenario_id` → 404; `build_tearsheet` raising `ValueError` (empty/missing-column results — it raises on both) → 422 with the message; missing DB → 503 (the `/health`-style gate). Never leak stack traces in responses; log them server-side via the repo's `logging` convention (entry points already `basicConfig(DEBUG)`).
- **Toolchain readiness (verified 2026-06-10).** Node `v24.15.0` / npm `11.12.1` are installed — the Vite/React side is ready, nothing to add. A `.venv` exists with `pandas 2.3.3` / `numpy 2.3.5` but **none of `fastapi`/`uvicorn`/`pydantic`/`pydantic-settings`/`orjson`** — those are the only Python additions, and `python-dotenv` is already present for `pydantic-settings`. **Python 3.14.4 — verified resolved (2026-06-10):** a strict wheel-only dry-run (`pip install --dry-run --only-binary=:all:`) resolves the full tree with **`cp314-cp314-win_amd64` wheels for every package, including the Rust extensions** (`pydantic-core 2.46.4`, `orjson 3.11.9`, `httptools 0.8.0`, `watchfiles 1.2.0`) — no source builds, no Rust toolchain needed (`uvloop` is correctly skipped on Windows). Verified install set to pin: `fastapi==0.136.3`, `uvicorn==0.49.0` (+ `starlette==1.2.1`), `pydantic==2.13.4`, `pydantic-settings==2.14.1`, `orjson==3.11.9`; dev: `httpx==0.28.1`. `orjson` stays in (the wheel exists) — but the §6 NaN/Inf→`null` sanitizer, not orjson, remains the actual guarantee of valid JSON.
- **Local dev run model.** Two processes:
  - API: `uvicorn api.main:app --reload --port 8000` (serves `/api/v1`, `/docs` Swagger UI, `/openapi.json`).
  - SPA: `npm run dev` in `frontend/` (Vite on `:5173`, proxying `/api` → `:8000`).
  - A `make dev` / `npm-scripts` / `tasks.json` convenience target can launch both. Production: `vite build` → static assets served by any static host (or mounted on FastAPI via `StaticFiles` for a single-process deploy).
- **Coexistence with Streamlit.** During migration both run side-by-side, reading the **same** `data/database.db`: Streamlit on `:8501`, the new stack on `:8000`/`:5173`. They are fully independent (Streamlit imports the engine in-process; the React app talks HTTP). Nothing about adding the API touches or breaks Streamlit. Streamlit is retired only after the React app reaches parity (§9, final phase) — and even then the files stay (repo convention: comment/retire, don't delete).
- **Determinism note.** The API is a *view* over already-computed, persisted results; it introduces no new stochasticity. `build_tearsheet` is a deterministic pure function of its input frames, so the tearsheet endpoint is referentially transparent (same DB state + params → identical JSON), which makes it trivially cacheable and testable.

---

## 9. Phased migration plan

Each phase is independently shippable; Streamlit stays up the whole time. Repo convention applies when any *existing* code is eventually touched (comment, don't delete) — but phases 1–6 add new code only.

| Phase | Deliverable | Touches | Independently shippable? |
|---|---|---|---|
| **0** | Scaffold `api/` (FastAPI app, `/health`, CORS, `pydantic-settings`, `serialization/` with NaN/date helpers + tests) and `frontend/` (Vite+TS, TanStack Query, OpenAPI type-gen, `HealthGate`). No business endpoints yet. | new `api/`, `frontend/`, `requirements.txt` (+fastapi/uvicorn) | Yes — proves the toolchain, serves nothing but health |
| **1 — FIRST VERTICAL SLICE** | **ETF Prices, end-to-end.** Endpoints 6 + 7 (`/etf-prices`, `/etf-prices/stats`) wrapping `db_reader.get_etf_history` + a `summaries.py` stat reducer; `EtfPricesPage.tsx` with `SeriesLineChart` + `DataTable`. | `api/routers/etf_prices.py`, `services/etf_prices.py`, `frontend/.../EtfPricesPage` | **Yes** — see rationale below |
| **2** | Scenario list (1) + NAV comparison (2) + returns scatter (3, Plotly WebGL). Locks in the `NamedSeries`/benchmark/summary patterns. | routers/services for backtest-results; `NavComparisonPage`, `ReturnsPage` | Yes |
| **3** | **Tearsheet (5) + daily rows (4)** — the real compute path. Serialize `build_tearsheet`'s `TearsheetResult`; `MetricGrid` + 3 charts + 3 tables. Add the tearsheet cache. | `routers/tearsheet.py`, `services/tearsheet.py`, `serialization/dataclasses.py`, `TearsheetPage` | Yes — the highest-value view |
| **4** | Volatility features (8,9) + Macro/yield-curve (10,11) + strategies introspection (12). Completes read parity with all six Streamlit views. | volatility/macro/strategies routers+services+pages | Yes |
| **5 (post-v1)** | Backtest job trigger (13,14): `BackgroundTasks` + in-process job registry + single-writer lock; `useMutation`+poll UI; cache invalidation on completion. Requires a small future refactor to make `run_backtest.main()` callable (out of this spec's no-edit scope). | `routers/jobs.py`, `services/jobs.py`; (later) wrap `run_backtest.py` | Yes — additive capability |
| **6** | Parity sign-off + retire Streamlit (stop launching it; keep files per convention; update README run instructions). Optionally serve the built SPA from FastAPI `StaticFiles`. | docs, run scripts | Yes |

**Recommended first vertical slice: ETF Prices (Phase 1).** Why this one:
- It is the **simplest complete loop**: one cheap reader (`get_etf_history`), one trivial server-side stat reduction, one line chart, one table — exercises *every* architectural layer (router → service → serialization → schema → React fetch → chart + table → formatting) with the least domain complexity.
- It has **no `scenario_id` dependency**, so it works even against a fresh/partial DB and decouples the first slice from the backtest results contract.
- It proves the **date/NaN/series serialization** and the **Recharts `NamedSeries` contract** that every later page reuses, so any kinks surface on the cheapest page, not on the tearsheet.
- (If a stakeholder demo needs the "wow" view first, the Tearsheet (Phase 3) is the alternative high-value slice — but it's a worse *first* slice because it couples the compute path, the dataclass serializer, and the metric grid all at once.)

---

## 10. Risks & trade-offs (honest assessment)

1. **Effort is concentrated in transport + serialization, not charting.** Because the dashboard is already Plotly over SQLite (§2), the bulk of the work is wrapping existing DB reads behind HTTP and getting the serialization boundary (§6) right — plus building the React app. There is no charting-logic rewrite. Scope the effort as low-to-moderate, weighted toward the tearsheet serializer and the NaN/date boundary, which is where the only real complexity lives.

2. **Compute/plot decoupling effort: LOW, concentrated.** `build_tearsheet` already returns pure data (dataclass of frames) — no decoupling needed. The only genuinely-trapped logic is the inline summary reductions in `nav_comparison.py`/`etf_prices.py` (~15 lines), which move to `services/summaries.py`. There is no place where numeric logic is welded inside a chart call.

3. **NaN/Inf serialization is the single most likely correctness bug.** `tearsheet_calculator` returns `np.nan` liberally (undefined ratios, first-252-row rolling windows, empty tails) and rolling-Sharpe divides through `safe_series_divide`. If the boundary doesn't sanitize, the API emits invalid JSON (`NaN` tokens) and the React parse fails *intermittently* (only for scenarios/early-windows that produce NaN). Mitigation is a one-liner applied centrally (§6) plus a dedicated `test_serialization.py` round-trip — but it must be done from the first endpoint, not retrofitted.

4. **Existing schema drift will leak into the API if copied naively.** The `gross_trade_notional`/`gross_notional` typo (§2.5) means the tearsheet's raw table silently omits a column today. If the API mirrors the Streamlit display list verbatim it inherits the bug. Mitigation: drive responses off the **canonical `db_reader.py` column lists**, standardize on `gross_trade_notional`. (Optional future patch — *not* part of this no-edit API work — fix the `tearsheet.py` display string and/or land the README's deferred "shared per-table column constants." Flagged, not bundled.)

5. **Payload size for the returns scatter.** Tens of thousands of points × N scenarios as `list[SeriesPoint]` is heavy JSON. Mitigations: the columnar `dates[]/returns[]` variant (§4.4), optional server-side decimation/downsampling for the overview, WebGL (`scattergl`) on the client, and gzip/br compression (uvicorn/proxy). The other views are small (daily series for ≤10 scenarios).

6. **Two readers, one truth.** `utils.py:load_backtest_results` (`SELECT *`) and `db_reader.py:get_backtest_results` (explicit columns) can disagree about which columns exist. Standardize the API on the **explicit reader** so the JSON contract is stable; do not use `SELECT *` behind an endpoint.

7. **Long-running job concurrency (only if Phase 5 is built).** Two concurrent backtests writing the same SQLite file via `INSERT OR REPLACE` would race and could interleave partial scenario writes. Mitigation: single-writer lock / one-slot executor (§5.1); the in-process model is correct *because* there is one DB and one writer. Choosing Celery/Redis here would add real ops burden for no benefit at single-analyst scale — deliberately rejected, with a documented upgrade path behind an unchanged 2-endpoint contract.

8. **Cache staleness on CLI-triggered backtests.** If the analyst runs `python run_backtest.py` from the shell (bypassing the optional job endpoint), the API's caches won't auto-invalidate. Mitigations: short TTLs (eventual freshness), a manual `POST /cache/flush`, or keying HTTP `ETag`/cache on the DB file mtime so a changed DB busts caches automatically. Acceptable; just must be a conscious choice.

9. **`build_tearsheet` raises on bad input.** It throws `ValueError` for empty results and for missing required columns, and for >1 `scenario_id` in the frame. The endpoint must catch these and map to 422/404 rather than 500 — and must pass a *single*-scenario frame (the service filters by `scenario_id`, which the canonical reader supports natively).

10. **Type-contract drift (Python ↔ TS).** If TS types are hand-written they'll diverge from the Pydantic models over time. Mitigation: generate `frontend/src/api/types.ts` from the live OpenAPI schema in CI (§7.4), the frontend mirror of the repo's existing pyright contract check on `EngineContext`. Without this, the contract guarantee is aspirational.

### Decisions resolved (2026-06-10)
All three previously-open questions are now settled (see the decisions log at the top):
- **Backtest-from-UI:** planned, **deferred to post-v1**. v1 is read-only; Phase 5 lands later. (Was: "is it wanted at all?")
- **Charting:** the **Recharts + Plotly split** is chosen (§7.1). (Was: split vs Plotly-only.)
- **Deploy target:** **v1 is local-only**; production-grade hosting deferred to a later version. Until then, auth / non-`*` CORS / TLS / hardened static-serving remain out of scope — and are gating requirements before any non-local exposure.

---

## 11. SemVer

This adds a **new, backward-compatible analytics surface** (a separate `api/` service + `frontend/` SPA) without changing the trading/engine API or any existing behavior. Under the repo's strict SemVer (x=breaking, y=feature, z=fix), introducing the FastAPI+React stack alongside Streamlit is a **minor feature bump** — from the current `V1.11.0`, the first shippable phase lands as **V1.12.0**. Subsequent phases that only add endpoints/pages remain minor bumps (or patches for pure fixups). Eventually **retiring Streamlit** (Phase 6) — removing a user-facing entry point — is the one step that could be argued as breaking *for anyone scripting against the Streamlit app*; in practice it's an internal tool swap, so it stays a minor bump with an explicit changelog callout, unless the team treats the dashboard URL as a stable external contract (then it's a major bump). The aspirational "Expected Timeline" headers in the README (`V1.2.0` "Full Analytics Dashboard", etc.) are labels, not literal SemVer targets, and don't constrain this numbering.

---

## 12. Deferred / out of scope

- Authentication, multi-user sessions, RBAC.
- Persisting the in-memory `trade_log` (currently written to no table) and exposing a trades endpoint — would need a new table + writer (engine-side change), out of this read-only spec.
- Surfacing the richer per-day `Decision` fields (conviction components, sized-vs-final weights, vol estimate/target/scale, notes) that the engine computes but doesn't persist — needs schema work first.
- Fixing the `gross_trade_notional`/`gross_notional` display typo and landing shared per-table column constants (README deferred item 8) — independent hardening patches, flagged in §10, not part of the API build.
- A PNG-figure endpoint for future heatmap/ribbon chart types (§4.5) — keep as a documented fallback, not a v1 feature.
- Serving the built SPA from FastAPI `StaticFiles` for single-process prod deploy (a Phase 6 nicety).
