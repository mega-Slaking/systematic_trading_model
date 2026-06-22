# Project Overview
## Current Version: V 1.21.4
![tests](https://github.com/mega-Slaking/systematic_trading_model/actions/workflows/tests.yml/badge.svg)

This project implements a systematic, rule-based trading strategy designed to tilt a portfolio between three U.S. Treasury–focused bond ETFs:

TLT: Long-duration Treasuries

AGG: Broad U.S. bond market

SHY: Short-duration “cash-like” Treasuries

The strategy uses a hybrid decision framework that combines:

- Price-based trend and momentum signals, which provide faster reaction to changing market conditions
- Macro-based direction and acceleration filters, which act as a slower-moving regime validation layer
- Volatility and covariance-aware position sizing, which adjusts exposure based on estimated asset and portfolio risk

The system is designed to participate in bond rallies when price and macro conditions are supportive, reduce duration exposure during tightening or unstable macro regimes, and rotate toward lower-risk bond exposure when conviction is weaker.

Rather than relying on explicit rate forecasts or discretionary assumptions about future policy decisions, the engine uses observable market and macro states to make systematic allocation decisions.


# Goal of the Strategy

The core goal of the strategy is to allocate across bond exposures based on the prevailing monetary and macro regime.

The engine aims to rotate toward assets that are better suited to the current environment, while reducing duration exposure when macro instability or inflation risk outweighs the expected reward.

In simplified terms:

- When disinflation and weakening growth conditions are supportive of duration, the strategy can increase exposure to longer-duration bonds such as TLT.
- When macro conditions are stable and non-accelerating, the strategy can favour a broader intermediate bond allocation such as AGG.
- When inflation pressure, policy uncertainty, or macro instability rises, the strategy can reduce duration exposure and rotate toward lower-duration assets such as SHY.

The strategy is designed to be:

- Simple enough to understand
- Systematic enough to reduce emotional decision-making
- Flexible enough to evolve through new signals, sizing methods, and scenario testing
- Grounded in economic reasoning rather than hindsight-fitted rules

# Core Assumptions

The strategy is built on the following economically motivated assumptions:

| Economic Condition | Policy / Market Interpretation | Preferred Duration Exposure |
|---|---|---|
| Inflation falling | Easing expectations may increase | Longer duration can benefit |
| Growth weakening | Defensive demand for bonds may rise | Longer duration can benefit |
| Growth stable and inflation non-accelerating | Policy environment may remain balanced | Broad bond exposure can be appropriate |
| Inflation accelerating | Tightening expectations may increase | Duration exposure should be reduced |
| High macro uncertainty | Risk control becomes more important | Lower-duration exposure may be preferred |

Bonds do not move only because yields have changed. They move because expectations about inflation, growth, policy, and risk have changed.

Macro data is slower-moving, while price data reacts faster:

- Price signals help with timing
- Macro signals help with validation
- Volatility and covariance estimates help with risk sizing

# Strategy Logic

At a high level, the strategy converts market and macro conditions into a systematic allocation decision across TLT, AGG, and SHY.

The engine does not rely on a single rule, moving-average crossover, or static macro lookup table. Instead, it uses a modular decision pipeline that separates signal generation, regime interpretation, conviction scoring, risk-aware sizing, and portfolio constraints.

## Signal Inputs

The strategy currently uses two main categories of signals:

### Price Signals

Price signals provide the faster-moving view of the market.

They are used to identify whether each asset is currently behaving favourably from a trend or momentum perspective. These signals help determine timing and whether the market is confirming the macro view.

Examples include:

- Recent return behaviour
- Trend / momentum direction
- Asset-level price confirmation
- Missing-price and data-quality checks

### Macro Signals

Macro signals provide the slower-moving economic context.

They are used to identify whether the broader environment is supportive or hostile for duration exposure.

The macro layer focuses on:

- Inflation direction
- Growth direction
- Macro acceleration or deceleration
- Labour-market strength or weakness
- Regime stability or instability

The purpose of the macro layer is not to forecast policy directly. Instead, it acts as a validation layer for deciding whether duration exposure is economically justified.

# Decision Framework

The strategy uses a decision framework rather than a fixed allocation table.

Each run produces a `Decision` object that carries the state of the strategy through the pipeline. This object is progressively enriched with:

- Price state
- Macro state
- Regime classification
- Conviction score
- Base allocation
- Volatility estimates
- Covariance estimates
- Sized weights
- Final constrained weights
- Rebalance instructions
- Trace/debug metadata

This makes the system easier to test, inspect, and extend.

## Allocation Intuition

The simplified economic logic is:

| Environment | Strategy Interpretation | Allocation Bias |
|---|---|---|
| Disinflation + weakening growth | Conditions may support duration | Increase long-duration exposure, typically TLT |
| Stable growth + non-accelerating inflation | Balanced bond environment | Favour broad bond exposure, typically AGG |
| Re-accelerating inflation or tightening pressure | Duration risk is less attractive | Reduce TLT exposure |
| High uncertainty or weak conviction | Risk control becomes more important | Rotate toward lower-duration exposure, typically SHY |


These are not hard-coded forecasts. They are economic priors that guide how the system interprets observable price and macro data.

The final allocation is then adjusted by the risk layer.

# Experimental Architecture

The strategy is designed to support controlled experimentation.

Different scenario configurations can be tested by changing the relevant config objects rather than rewriting the strategy logic.

Examples of configurable experiments include:

- Volatility estimation method
  - Rolling standard deviation
  - EWMA volatility
  - GARCH volatility

- Volatility scaling behaviour
  - Scaling on/off
  - Different volatility lookback windows
  - Different volatility scaling powers

- Covariance modelling
  - Sample covariance
  - EWMA covariance
  - Portfolio volatility targeting

- Allocation profiles
  - Current base allocation logic
  - Legacy conviction-driven allocation logic
  - Future strategy variants

- Conviction profiles
  - Conviction disabled
  - Conviction-driven sizing
  - Future macro/price confidence models

The goal is to make strategy development empirical. Instead of relying on a single backtest result, the system can compare multiple strategy configurations under the same data, execution, cost, and portfolio assumptions.

# Experimental Findings

Running the strategy registry through the experimental backtesting framework produced a clear and somewhat counterintuitive result: **the risk-layer machinery — position-sizing method, asset-wise volatility scaling, and covariance-based portfolio volatility targeting — had negligible effect on realised capital gains.** The most profitable configurations of the strategy were those that *did not* apply covariance scaling or asset-wise volatility scaling, or that used low volatility-scaling powers. The cumulative return is driven overwhelmingly by the regime-conditional allocation across TLT/AGG/SHY, not by the volatility normalisation applied on top of it.

This is consistent with Harvey et al. (2018) [^harvey2018], who studied the impact of volatility targeting across asset classes and found that while volatility targeting improved risk-adjusted returns (Sharpe ratio) for equities, it had **essentially no effect on the Sharpe ratio of government bonds**. Our findings extend the same intuition to this bond-rotation strategy: because the underlying duration exposures are already relatively well-behaved in volatility terms, the additional volatility- and covariance-based normalisation contributes little incremental performance and, in the most profitable variants, is best left off or heavily damped.

[^harvey2018]: Harvey, C. R., Hoyle, E., Korgaonkar, R., Rattray, S., Sargaison, M., & van Hemert, O. (2018). *The Impact of Volatility Targeting*. SSRN Working Paper. <http://dx.doi.org/10.2139/ssrn.3175538>

# Running the App

## Analytics dashboard (FastAPI + React)

The dashboard is a **React single-page app served data by a FastAPI service** (see
`docs/fastapi_react_migration_spec.md`). It reads the persisted results in
`data/database.db` and reuses the existing Python compute behind a read-only REST
API. Run two processes from the repo root:

- **API**: `uvicorn api.main:app --reload --port 8000` — serves `/api/v1`, plus
  `/docs` (Swagger UI) and `/openapi.json`.
- **SPA**: `npm --prefix frontend run dev` — Vite dev server on
  `http://localhost:5173`, which proxies `/api` → `:8000`.

Then open **http://localhost:5173**. One-time dependency setup:
`pip install -r requirements.txt` (API) and `npm --prefix frontend install` (SPA).
The seven tabs cover NAV comparison, returns, the tearsheet, ETF prices,
volatility features, ETFs vs macro, and the strategy registry.

## Running a backtest

- From the shell: `python run_backtest.py` — runs the whole strategy registry and
  persists the results to `data/database.db`.
- Or from the dashboard: the **Strategies** tab has a "Run backtest" button (the
  same engine, behind the `/api/v1/jobs` endpoints).

## Legacy Streamlit dashboard (retired in V1.15.0)

The original Streamlit dashboard under `streamlit/` is **retired but not deleted**
— it is kept as a reference / rollback and still runs against the same
`data/database.db`:

```
streamlit run streamlit/app.py
```

It is now **frozen**: new analytics (e.g. the Strategies tab and the
backtest-from-UI trigger) land only in the FastAPI + React stack, so Streamlit
will drift behind over time. The React app reached parity with all six Streamlit
views in V1.13.0.

# Testing

A `pytest` suite lives under `tests/` (see `tests/TEST_PLAN.md` for the full blueprint and coverage map).

- Run everything: `python -m pytest`
- Fast loop (skips the slow GARCH fit and backtest e2e): `python -m pytest -m "not slow"`

It runs automatically in two places:
- **CI** — GitHub Actions (`.github/workflows/tests.yml`) on every push to `main`/`dev` and on pull requests.
- **Pre-commit** — a local hook runs the fast suite before each commit. Enable once with `pip install -r requirements-dev.txt` then `pre-commit install`.

# Additions:
## V 1.1.0
- Isolated Backtesting pipeline (separated process to live decision making)
- Backtest Analytics (nav, drawdown, exposure)
- Email integration to notify daily trade decision
- Reshaped ETF price data at ingestion to enforce deterministic backtesting
## V 1.2.0
- Added visualization functions for regime analysis
Added Buy & Hold comparisons for TLT, AGG, SHY
Added regime plotting (inflation, growth, labour, curve state, macro supports duration)

- Added decision_trace and regime_trace lists to track decisions and regimes during backtest and live

- Added rule_id field to decision output for better traceability
Assigned specific rule IDs to each decision pathway (e.g., "INF_SHY_001", "DIS_INV_TLT_001")

- Converted all plots to return figure objects (easier composition)
Added build_buy_and_hold_nav() for benchmark comparisons
Added 5 new regime visualization functions with color coding

- Added Streamlit dashboard application with multi page views for analytics

## V 1.3.0
- Added explicit execution and transaction cost modeling, with fee cost, slippage cost, and total transaction cost tracked per day

- Introduced Trade objects to represent individual BUY / SELL executions, with per-trade execution properties (price, notional, costs, reason) persisted for analytics

- Implemented realistic rebalance execution pipeline

- Trades now update portfolio cash and holdings using executed prices and fees

- Rebalance logic produces auditable SELL → BUY trade sequences on asset switches

- Daily NAV is now derived from post-trade cash and holdings

- Cumulative transaction cost impact visible across full backtest horizon

- Introduced accounting and valuation layers to separate execution, valuation, and accounting concerns, execution: generates trades with prices and costs,
valuation: marks portfolio to market at mid prices, accounting: aggregates daily performance and trading activity

## V 1.4.0

- Introduced multiposition portfolio with weights and constraints

## V 1.4.1

- SQL refactor for data storage and reading

## V 1.4.2

- Migrated decision output from ad-hoc dictionaries to strongly-typed `Decision` dataclass

- Created modular 4-stage decision pipeline: regime evaluation → base weight allocation → position sizing → constraint application

- New engines: `regime_engine.py` (macro regime classification), `base_allocator_engine.py` (allocation logic from v2), `position_sizer_engine.py` (volatility/conviction scaling), `constraint_engine.py` (hard constraints)

- Introduced `decision_orchestration.py` to coordinate pipeline stages with signal data and configuration

- Refactored consuming modules to use Decision properties instead of dict access: `run.py`, `portfolio.py`, `notifier.py`, `backtest.py`, `decision_trace.py`, `persister.py`

## V 1.5.2

- **Fixed t-1 data lag issue**: Changed data filtering in `BacktestContext` and `VolatilityEstimator` from `<=` to `<` to prevent look-ahead bias. Signals now use t-1 data when making t-day decisions.

- **New object-oriented approach for decision pipeline**:
  - Core design: A single strongly-typed `Decision` dataclass flows through four modular, composable engines (`regime_engine`, `base_allocator_engine`, `position_sizer_engine`, `constraint_engine`), accumulating state at each stage
  - Each engine reads relevant fields from the `Decision` object, computes outputs, and returns an updated `Decision` instance—enabling clean composition and immutability
  - Introduced parameterized `PositionSizingConfig` with volatility and conviction scaling parameters (`vol_scaling_power`, `use_covariance_scaling`, `target_portfolio_vol`) for scenario flexibility
  - Pipeline now supports optional volatility estimates and covariance matrices fed into the `Decision` workflow, enabling risk-aware position sizing and multi-scenario backtesting
  - Clean separation of concerns: each engine can be independently tested, reused, or evolved without affecting others

- **New Volatility Framework**: 
  - Added `src/volatility/` module with `estimator.py` for asset-level volatility computation and `portfolio_vol_estimator.py` for portfolio-level volatility
  - Created `VolatilityRequest`, `VolatilityEstimate`, and `PortfolioVolResult` dataclasses in `models.py`
  - Integrated rolling standard deviation volatility computation into decision pipeline

- **Scenario Testing Infrastructure**:
  - Created `src/scenarios/` module with `factory.py` and `models.py` for parameterized backtest scenario definition
  - Added `BacktestScenario` dataclass to bundle volatility config, position sizing parameters, and allocation profiles
  - Implemented `build_vol_power_scenarios()` for running multi-scenario backtests with varying volatility scaling powers
  - Updated `run_backtest.py` to loop through scenarios and tag all results with `scenario_id`

- **Database Schema Updates**:
  - Added `scenario_id` column to `backtest_results`, `backtest_decision_trace`, and `backtest_regime_trace` tables in `db_writer.py`
  - All backtest output now flows to database only (removed CSV saving for test results)

- **Streamlit Enhancements**:
  - Added new `scenario_testing.py` page with 4-tab dashboard: NAV Comparison, Returns Analysis, Detailed Metrics, ETF Prices
  - NAV Comparison now includes buy-and-hold benchmarks (TLT, AGG, SHY) for performance comparison
  - Historical ETF price visualization with statistics (first/last close, min/max, total return)

- **Code Cleanup**:
  - Deleted dead code: `decision_engine.py`, `decision_engine_v2.py`, `backtest_persister.py`, `src/sizing/` module
  - Removed CSV export for backtest results in `fetch_etf_prices.py` and `fetch_macro_data.py` (DB-only storage)
  - Cleaned up imports: Consolidated `build_portfolio_vol_result` export in `volatility/__init__.py`

- **API Changes**:
  - `run_backtest()` now accepts `scenario` parameter for configuration
  - `run_engine()` now accepts `scenario` parameter and computes portfolio volatility
  - `size_positions()` refactored to accept `VolatilityEstimate` object instead of raw dict
  - `PositionSizingConfig` extended with `vol_scaling_power` parameters

## V 1.6.2

- **New Covariance Module (`src/covariance/`)**: 
  - Added `estimator.py` for rolling covariance matrix computation
  - Created `models.py` with `CovarianceRequest` and `CovarianceMatrix` dataclasses for type-safe covariance workflow
  - Covariance matrices are computed on rolling windows of returns with configurable half-life for exponential weighting
  - Supports flexible asset lists and lookback periods for scenario-based testing

- **Portfolio-Wide Volatility Targeting with Cash Treatment**:
  - SHY is treated as a cash-equivalent asset (matched in covariance matrix and position sizing)
  - Portfolio volatility target is specified in `PositionSizingConfig` with `target_portfolio_vol` parameter
  - Position sizing now scales weights to hit target portfolio volatility while respecting SHY as cash reserve
  - Portfolio vol computed from active asset weights (TLT/AGG) using covariance matrix; SHY provides downside cushion without participating in covariance drag

- **Covariance-Aware Position Sizing**:
  - Position sizing engine now integrates covariance-based portfolio volatility computation
  - When `use_covariance_scaling` is True in scenario config, position sizes are scaled to match target portfolio volatility

- **Enhanced Scenario Framework for Volatility Testing**:
  - Extended `BacktestScenario` to include `target_portfolio_vol` list for multi-volatility backtests
  - New `build_vol_target_scenarios()` in `scenarios/factory.py` generates scenarios across target volatility range

  ## V 1.7.2

- **Advanced Volatility Estimation Methods**:
  - Implemented EWMA (exponential moving average) volatility estimation with configurable decay parameter (λ=0.94 default)
  - Implemented GARCH(1,1) volatility estimation with conditional heteroscedasticity modeling via `arch` library

- **EWMA Covariance Matrix Estimation**:
  - Implemented `_estimate_ewma_cov()` in covariance estimator for exponentially-weighted correlation structure

- **Extended Scenario Factory for Risk Model Comparison**:
  - Added `build_ewma_covariance_scaling_scenarios()` to generate backtests combining rolling asset vol with EWMA covariance matrices
  - Scenario naming: `baseV1_roll20_ewmacov_lam{lambda}_tv{target_vol}_convOff` for clear identification

- **Backtest Date Range Refinement**:
  - Constrained backtest start date
  - Ensures sufficient historical data for GARCH model initialization (100+ day minimum history) and stable covariance estimation

- **Configuration & Schema Updates**:
  - Added `ewma_lookback_days` parameter to `CovarianceConfig` (default 756 days ~3 years) for EWMA covariance window control
  - Extended `VolatilityConfig` with GARCH parameters: `garch_mean`, `garch_dist`, `garch_rescale_returns`, `garch_lookback_days`
  - Updated `build_scenario()` factory to accept and propagate `ewma_lambda` to both volatility and covariance configs

  ## V 1.8.2

- **Expanded Macro Data Fetching via FRED**:
  - Updated FRED data ingestion to include a broader macro dataset for regime classification and conviction scoring
  - Added/standardised key macro series including inflation, core inflation, unemployment, payrolls, Treasury yields, Fed funds, credit stress, sentiment, and jobless claims
  - Improved macro input coverage for monetary policy, economic health, labour market weakness, credit stress, and duration-support signals

- **Lean Macro Database Schema**:
  - Refactored macro storage to keep the database focused on raw fetched series only
  - Removed derived fields from persistent storage, including YoY inflation, yield curve, inflation direction, regime flags, and confidence/stress indicators
  - Moved derived macro feature computation into runtime signal processing via `compute_macro_signals()`
  - Reduces stale derived-data risk and keeps signal logic centralised in the macro signal engine

- **Monetary and Economic Regime Classification**:
  - Extended the decision pipeline to classify macro environment into separate monetary and economic regimes
  - Monetary regime now supports `dovish`, `hawkish`, and `neutral` classifications
  - Economic regime now supports `bullish`, `bearish`, and `neutral` classifications
  - Combined regime labels such as `dovish_neutral`, `hawkish_bearish`, and `neutral_bullish` are now stored on the `Decision` object for traceability

- **Asset-Level Conviction Scaling Engine**:
  - Added a new conviction scaling layer to tilt allocations after base allocation and before risk sizing
  - Conviction is calculated at the asset level using macro evidence, favourable-asset direction, and price-trend confirmation
  - Added support for price steepness through volatility-normalised moving-average slope signals
  - Conviction outputs are stored separately as multipliers, component scores, raw scores, and conviction-adjusted weights for better debugging and scenario attribution

- **Pipeline Support for Legacy Allocation Engine**:
  - Added support for calculating legacy signal-weighted base allocations alongside the newer direction-neutral base allocation approach
  - Legacy allocation logic remains available for controlled comparison against the current conviction-based allocation flow
  - Position sizing can now select the starting weight source via configuration, including `conviction` or `legacy`
  - This allows legacy and current allocation methods to be tested under the same risk-sizing and covariance-scaling framework

- **Scenario Factory Extensions for Legacy Comparisons**:
  - Extended scenario configuration to support `starting_weight_source`
  - Added legacy allocation scenario variants for covariance scaling and EWMA covariance experiments
  - Enables direct comparison between legacy base allocation and current conviction-adjusted allocation under matched volatility/covariance assumptions

- **Front-End Scenario Analytics Enhancements**:
  - Added analytics views for comparing scenario-level performance across allocation and risk-model variants
  - Scenario comparison now supports return, max drawdown, volatility, and other risk/return metrics across backtest runs
  - Provides a cleaner teardown workflow for understanding whether outperformance is driven by allocation logic, duration exposure, covariance scaling, or volatility targeting

  ## V 1.8.3
   
- **C++-Accelerated Covariance Matrix Computation**:
  - Added an initial C++ computation path for covariance matrix estimation to improve backtest runtime performance
  - Moved the most calculation-heavy covariance operations out of pure Python/Pandas and into compiled C++ logic
  - Exposed C++ covariance functions to Python via `pybind11`

  ## V 1.8.4

- **Precomputed Returns View for Covariance Estimation**:
  - Added a precomputed covariance returns view to avoid rebuilding aligned return matrices on every backtest date
  - Refactored covariance estimation to reuse a shared `returns_wide` representation instead of repeatedly copying ETF history, converting dates, sorting, calculating percentage returns, pivoting, and dropping missing rows
  - Added a `CovarianceReturnsView` path for slicing return windows by `as_of_date` and lookback configuration
  - Updated the backtest flow to build the returns view once before running scenario batches and pass it through the backtest context
  - Keeps covariance estimation behaviour consistent while reducing repeated Pandas preprocessing overhead

- **Covariance Matrix Cache Across Scenario Runs**:
  - Added covariance estimate caching on the precomputed returns view
  - Cache keys are based on covariance-specific inputs including date, tickers, covariance method, lookback window, EWMA lookback window, minimum history, annualisation factor, and EWMA lambda
  - Enables covariance matrices to be reused across scenario variants where sizing parameters differ but covariance assumptions are identical
  - Prevents unnecessary recalculation across target-volatility scenario grids while preserving separate covariance outputs for distinct methods, lookbacks, and EWMA lambda values
  - Added cache hit/miss tracking to support debugging and performance validation during scenario runs

  ## V 1.8.5

- **Dynamic Tearsheet Analytics Layer**:
  - Added a dedicated tearsheet analytics flow for evaluating each backtest scenario beyond NAV comparison alone
  - Introduced structured tearsheet models for separating summary metrics, equity curve data, drawdown curve data, rolling metrics, exposure summaries, and regime summaries
  - Refactored tearsheet calculation into a reusable accounting/analytics layer so Streamlit renders computed outputs instead of owning the metric logic
  - Keeps tearsheet metrics dynamically computed from persisted backtest results rather than storing derived analytics in the database

- **Expanded Scenario Performance Metrics**:
  - Added full-period performance and risk metrics including total return, CAGR, annualised volatility, Sharpe ratio, Sortino ratio, max drawdown, Calmar ratio, historical VaR, historical CVaR, skew, excess kurtosis, worst day, and best day
  - Added rolling metric outputs for time-series analysis of rolling return, rolling volatility, and rolling Sharpe

- **Exposure and Allocation Diagnostics**:
  - Added exposure summary calculations using stored portfolio weights from backtest results
  - Computes average asset weights for TLT, AGG, and SHY to show how each scenario allocates across duration and defensive assets over time
  - Helps diagnose whether weak or strong scenario performance is driven by excessive concentration, insufficient defensive allocation, or persistent duration exposure

- **Regime-Based Performance Breakdown**:
  - Integrated `regime_trace` into the tearsheet workflow using scenario-aligned regime data by date and `scenario_id`
  - Added regime summary analytics across inflation regime, growth regime, labour regime, curve state, and macro duration-support state
  - Computes return, volatility, drawdown, worst day, best day, and average asset weights within each regime bucket
  - Enables analysis of where each scenario performs well or breaks down across different macro environments

- **Streamlit Tearsheet Integration**:
  - Added a dedicated tearsheet tab to the scenario testing dashboard
  - Updated the frontend to pass selected scenario results and matching regime trace data into the tearsheet builder
  - Added tearsheet display sections for summary metrics, equity curve, drawdown curve, rolling metrics, exposure summary, regime summary, full summary table, and raw scenario data
  - Added regime trace match-rate debugging to validate date and scenario alignment between backtest results and regime trace data

  ## V 1.8.6

- **Tearsheet Metrics Framework**:
  - Introduced structured metric models in `tearsheet_models.py` to represent calculated tearsheet outputs in a consistent format
  - Added trade/return quality metrics including daily hit rate, payoff ratio, profit factor, average win day, and average loss day
  - Provides a cleaner foundation for comparing whether scenario performance is driven by returns, risk control, drawdown behaviour, or consistency of positive return days

- **Tearsheet Calculation Layer**:
  - Added `tearsheet_calculator.py` to centralise tearsheet metric calculations from persisted backtest results
  - Keeps metric formulas separated from Streamlit rendering logic for improved testability and maintainability
  - Calculates scenario-level statistics from daily NAV/return data, enabling consistent comparison across different strategy configurations
  - Supports better debugging of weak scenarios by exposing whether performance issues come from low hit rate, poor payoff ratio, excess volatility, or drawdown behaviour

- **Tearsheet Builder Layer**:
  - Added `tearsheet_builder.py` to assemble tearsheet outputs from raw backtest result data
  - Provides a structured bridge between stored scenario results and front-end display components
  - Improves separation of concerns by keeping data preparation, metric calculation, and UI rendering in separate layers
  - Establishes a reusable pattern for extending analytics with future metrics such as VaR, rolling drawdowns, exposure attribution, carry analysis, and regime-level performance breakdowns

- **Streamlit Front-End Refactor**:
  - Refactored the Scenario Testing Dashboard into separate tab rendering modules under `home_page_tabs`
  - Split major dashboard views into dedicated render functions:
    - `render_nav_comparison_tab()`
    - `render_returns_analysis_tab()`
    - `render_tearsheet_tab()`
    - `render_etf_prices_tab()`
  - Simplified the main Streamlit app so it now acts primarily as the dashboard entry point and tab orchestrator
  - Moved shared loading/configuration utilities into `home_page_tabs.utils`, including `load_backtest_results` and `DB_PATH`
  - Improves front-end maintainability by separating NAV comparison, returns analysis, tearsheet analytics, and ETF price inspection into isolated scripts
  - Creates a cleaner structure for adding future analytics tabs without bloating the main dashboard file

- **Scenario Analytics Workflow Improvements**:
  - Improved the ability to compare strategy variants using both performance metrics and behavioural diagnostics
  - Supports more disciplined strategy iteration by making it easier to distinguish between high-return, high-risk, and genuinely risk-adjusted improvements
  - Provides a stronger analytics layer for validating covariance scaling, volatility targeting, allocation logic, and future strategy experiments
  - Establishes the tearsheet as the main evaluation layer for determining whether scenario changes are actually improving strategy quality

  ## V 1.9.0

- **Volatility Feature Surface Module (`src/volatility/feature_surface.py`)**:
  - Added a precomputed asset-level volatility feature surface spanning the full `date × ticker` panel, built once and reused across all scenarios (analogous to the covariance returns view)
  - Computes multiple volatility estimates per asset in a single structure: rolling standard deviation (20d, 60d) and EWMA (λ=0.94, λ=0.97), plus comparison features (EWMA-to-rolling ratios and 5-day EWMA change)
  - Conceptually separated from the existing point-in-time `estimator.py`: the surface exposes many volatility views as signals/diagnostics, while the estimator still produces the single selected volatility used for sizing
  - Added in-memory caching keyed on tickers, config, price column, lag, and the date range, with `clear_volatility_feature_surface_cache()`
  - Lookahead-safe by construction: all feature columns are lagged one day (`lag_features_days=1`) so each date only carries volatility known *before* that date, matching the estimator's `date < as_of_date` rule

- **GARCH(1,1) Volatility in the Feature Surface**:
  - Added GARCH(1,1) as an opt-in surface feature (`include_garch`) using the `arch` library, reusing the existing estimator's fit recipe
  - Implemented a monthly-refit + daily roll-forward design: the expensive optimisation is refit only at the configured `garch_refit_frequency` (daily/weekly/monthly), and the conditional variance is rolled forward each day with the held parameters, keeping the feature responsive without per-day refitting
  - Validated to reduce exactly to the point-in-time estimator when refit daily (0.00e+00 difference)

- **New Volatility Feature Config & Surface Models (`src/volatility/models.py`)**:
  - Added `VolatilityFeatureConfig` (rolling windows, EWMA lambdas, GARCH parameters, refit frequency, annualisation, minimum history) with a `cache_key()` for safe caching
  - Added `VolatilityFeatureSurface` carrying the feature panel with `get_snapshot(as_of_date)` and `get_ticker_snapshot(as_of_date, ticker)` accessors

- **Passive Backtest Integration**:
  - The feature surface is built once before the scenario loop and attached to `BacktestContext` (beside the returns view), shared read-only across scenarios
  - The engine retrieves the daily snapshot into `context.volatility_features` each date via `get_volatility_snapshot()` / `volatility_snapshot_to_dict()`
  - Integration is deliberately passive: features are made available for diagnostics and future signals, but allocation/strategy logic is unchanged

- **Volatility Feature Persistence**:
  - Added a scenario-independent `volatility_features` table (one row per `date, ticker`, storing all feature columns plus a `config_key`)
  - Added `insert_volatility_features()` in `db_writer.py` and `get_volatility_features()` in `db_reader.py`
  - `run_backtest.py` persists the surface once per run (outside the scenario loop) so the front-end reads the exact lagged values the strategy saw

- **Streamlit Volatility Features Tab**:
  - Added a new "Volatility Features" tab to the Scenario Testing Dashboard
  - Renders per-asset annualised volatility estimates over time (rolling 20/60, EWMA 0.94/0.97, GARCH) with a method selector and a latest-values table
  - Added `load_volatility_features()` to `home_page_tabs.utils`, guarded to degrade gracefully when the table is empty

- **Volatility Feature Validation Suite**:
  - Added `tests/feature_surface_test.py` cross-validating the surface against the point-in-time estimator across random dates
  - Confirms rolling and EWMA match to floating-point precision, GARCH matches exactly under daily refit, and comparison-ratio features are self-consistent
  - Doubles as a lookahead check: agreement with the `date < t` estimator confirms the surface uses no data on or after each date

  ## V 1.9.1

- **Test Suite**:
  - Added a `pytest` suite under `tests/` (~182 tests) covering pure mechanics (weights, valuation, day metrics, rebalance), the decision pipeline (regime → favourable-asset → base allocation → conviction → sizing → constraints), volatility and covariance estimation, the volatility feature surface, execution/accounting, tearsheet analytics, persistence round-trips, and a full backtest end-to-end run
  - Organized by domain (`data/`, `features/`, `backtest/`, `strategy/`, `tearsheets/`, `persistence/`), with the full blueprint and coverage map in `tests/TEST_PLAN.md`
  - Dedicated regression guards for lookahead safety, determinism, and money/weight invariants

- **Coverage**:
  - Wired `pytest-cov` with a scoped `.coveragerc` that excludes external I/O, visuals, and the deferred live path; in-scope line coverage is ~82%
  - Run locally with `python -m pytest --cov=src --cov-report=term-missing`

- **Continuous Integration**:
  - Added a GitHub Actions workflow (`.github/workflows/tests.yml`) running the suite on pushes to `main`/`dev` and on pull requests
  - Added a local pre-commit hook (`.pre-commit-config.yaml`) running the fast suite before each commit
  - Added `requirements-dev.txt` (pytest, pytest-cov, pre-commit)

- **Bug Fix**:
  - Fixed `get_backtest_results` in `db_reader.py` selecting a non-existent `gross_notional` column (the column is `gross_trade_notional`), which raised `OperationalError` on every call; surfaced and regression-guarded by the new persistence round-trip tests

  ## V 1.9.2

- **Live Run Fixes**:
  - Repaired the live daily-run path (`run_engine` via `LiveContext`), which had drifted out of sync with the backtest. `run_engine` now builds a covariance returns view when the context does not supply one, and treats the volatility-surface hooks as optional, so running with a `LiveContext` no longer raises `AttributeError`
  - Fixed `LiveContext.get_selected_price_today` to use `PriceNormalizer.normalize_prices` (it previously called a method that did not exist)

- **Report Deprecation**:
  - Deprecated `generate_daily_report` (the matplotlib daily report); it is no longer wired into the live run and `LiveContext.visualize` is now a no-op. This removes a `KeyError` that occurred when raw macro data was passed to plots reading derived columns such as `cpi_yoy`

- **Live Path Test Coverage**:
  - Added `tests/live/` exercising the live decision path end-to-end (decision output, recorded decision/regime traces, lazy returns-view build), the price-lookup fix, the deprecated no-op `visualize`, and that the live run invokes its persist/notify hooks

- **Repository Hygiene**:
  - Fixed an over-broad `.gitignore` rule (`data/`) that was unintentionally ignoring the `tests/data/` test folder; anchored it to `/data/` so test code is tracked while the root data directory stays ignored

  ## V 1.9.3

- **Code Cleanup (no behaviour change)**:
  - Removed duplicate `get_cached_covariance` / `set_cached_covariance` / `clear_covariance_cache` definitions in `CovarianceReturnsView`; the first set was dead code, silently overridden by the cache hit/miss-tracking versions
  - Dropped the unused `generate_single_asset_rebalance_trades` import/export (superseded by `rebalance_v2`) and marked `src/execution/rebalance.py` as deprecated
  - Deleted the redundant print-based `tests/feature_surface_test.py` (superseded by `tests/features/test_volatility_surface.py`) and removed its stale pytest `--ignore`

- **Repository Hygiene**:
  - Stopped gitignoring the database schema: `.gitignore` now uses `/data/*` with a `!/data/db_population.py` exception, so the canonical `CREATE TABLE` definitions are tracked while the database and raw data stay ignored
  - Fixed assorted typos across comments and identifiers

  ## V 1.9.4

- **Configuration Consolidation (no behaviour change)**:
  - Centralized the tradable asset universe in `src/universe.py`; the six modules that each re-declared `["TLT", "AGG", "SHY"]` now import a single `UNIVERSE` constant, which also resolved an ordering inconsistency with `config.TICKERS`
  - Centralized the sqlite database location in `src/storage/paths.py`; readers, writers, fetchers, and `run_backtest.py` now import one `DB_PATH` instead of four hardcoded variants (and `persister.py` no longer depends on `config`)

- **Logging**:
  - Replaced ad-hoc `print()` statements across the backtest engine, fetchers, notifier, and runner with module-level loggers (`logging.getLogger(__name__)`), defaulting to `debug` level; entry points (`run_backtest.py`, `main.py`) configure logging so output is shown when running the app but stays quiet under tests
  - Missing-required-ticker conditions are logged at `warning` level

  ## V 1.9.5

- **Engine Context Contract (`EngineContext`)**:
  - Added `src/context/protocol.py` — a runtime-checkable `Protocol` describing the interface `run_engine` requires of a context. `BacktestContext` and `LiveContext` satisfy it structurally; this guards the drift that previously broke the live run (`run_engine` reaching for a member a context didn't provide)
  - Enforced two ways: a runtime `isinstance` conformance test (`tests/context/`) and a static `pyright` check in CI scoped to the protocol + `run_engine` (`pyrightconfig.json`; `pyright` added to dev dependencies and the CI workflow)
  - Declared `returns_view` in `BacktestContext.__init__` so the context shape is explicit rather than attached externally

- **Importable Without Secrets**:
  - `config.py` no longer raises at import when API keys are absent. The dead `FMP_API_KEY` (superseded by yfinance) was removed and `FRED_API_KEY` is validated lazily inside `fetch_macro_data`, so the package imports with no `.env` present — tests and CI require no secrets

- **Execution Boundary Cleanup (no behaviour change)**:
  - Removed weight re-normalisation from `Portfolio.rebalance_v2`; the execution layer now trusts the decision layer's canonical weights (`apply_constraints` owns shaping). This is behaviour-preserving today, and unblocks future sub-1.0 cash buffers and signed/short weights that the old normalisation would have silently flattened

  ## V 1.10.0

- **Unified, Selectable Strategy Configuration (`src/strategy/`)**:
  - Added `StrategyConfig` (`src/strategy/config.py`) — a single, frozen config that composes the five existing sub-configs (`VolatilityConfig`, `CovarianceConfig`, `PositionSizingConfig`, `ConvictionConfig`, `WeightConstraints`) into one source of truth shared by backtest and live. This is the config-side peer to V1.9.5's `EngineContext` Protocol (the Protocol unified the *interface*; this unifies the *config*)
  - Added a `.with_(**overrides)` helper that flips any knob by name (e.g. `use_covariance_scaling`, `target_portfolio_vol`, `shy_floor`) without the caller knowing which nested sub-config owns it, returning a new immutable config. Toggling a risk feature on/off is now a one-liner instead of a factory edit
  - Design spec: `docs/strategy_config_design_spec.md`

- **Named Strategy Registry (`src/strategy/presets.py`)**:
  - Added `STRATEGIES`, a flat dict of concrete, named configs built from `grid(...)` sweep helpers, replacing the five `src/scenarios/factory.py` builder functions
  - Reproduces all 22 historical scenarios with their exact prior names (so `scenario_id`-tagged history is preserved) and adds `default` (the live-equivalent config that was never previously backtested) → 23 entries; `run_backtest.py` now iterates the registry, so adding a scenario is a one-line registry edit with no run-script changes
  - Adding a new knob now costs one line in the `_FIELD_OWNERS` map instead of editing the factory signature, body, and every builder

- **Conviction + Constraints Now Configurable Per Run**:
  - `run_engine` now forwards `conviction_config` and `constraints` into the decision pipeline; previously both were accepted by `orchestrate_decision_pipeline` but never passed, so they were silently pinned to defaults on every run. Conviction parameters and the SHY floor / eligibility are now sweepable
  - Behaviour-preserving: forwarding the explicit defaults is byte-identical to the old implicit `None` (verified by the backtest determinism/NAV and live regression tests)

- **Live Strategy Selection**:
  - Added `LIVE_STRATEGY` + `live_strategy()` in `src/strategy/presets.py`; `main.py` now trades exactly one selected registry entry (`run_engine(context, strategy=live_strategy())`). Switching the live book is a one-line change, and a bad name fails fast with the list of valid names
  - The live run was moved off the previous implicit default onto a validated registry entry (currently `baseV1_roll20_ewmacov_lam94_tv05`). Email notification and DB persistence are unchanged

- **Migration & Safety**:
  - Old code (the `run_engine` config fork, the `run_backtest.py` scenario list, and the five factory builders) is commented out rather than deleted, per the repo's refactor convention, as a rollback safety net; `build_scenario` / `BacktestScenario` remain as the back-compat path
  - Added `tests/strategy/test_strategy_config.py` and `tests/strategy/test_presets.py`; full suite green (210 passed)
  - Clarified that `base_allocation_profile` is an inert identifier label (the functional base-allocation switch is `starting_weight_source`); left in place, slated for later cleanup

  ## V 1.11.0

- **New TLT-Tracking Base Strategy (`src/strategy/tlt_tracker.py`)**:
  - Replaced the modern regime-table allocator with a TLT-chasing strategy: it follows TLT on confirmed uptrends (with a deliberate lag) and buffers into AGG/SHY on confirmed downtrends, to capture duration upside while cutting the left tail
  - Stateful machine: a Schmitt-trigger hysteresis band on TLT's `ma_slope_z`, an `entry_confirm_days` confirmation lag (slower in) with a faster asymmetric `exit_confirm_days` (faster out), a `min_hold_days` dwell floor, and weight ramps (`ramp_step` up, `ramp_step_down` down) toward per-state targets (`tlt_max` / `tlt_neutral` / `tlt_min`, `agg_defensive`, `shy_min`). All knobs live in a frozen `TltTrackerConfig`
  - Reuses the existing macro/monetary signals as confirmation/veto: a stagflation/hawkish regime caps TLT (`macro_veto`), relaxed when `macro_supports_duration` confirms (`macro_confirm`)
  - Look-ahead-safe and deterministic: the state machine is *replayed* over the point-in-time TLT signal history each day (the backtest only exposes rows dated `< current_date`), carrying no mutable cross-day state. Trend detection reuses the engine's precomputed `ma_slope_z` / `trend_up` / `ret_lookback`
  - Writes both `base_weights` and `conviction_weights`, so the position sizer (`starting_weight_source="conviction"`) consumes the tracker's directional weights with no sizer changes; the conviction tilt is bypassed (the tracker *is* the directional layer). The vol/cov/constraint risk overlay still runs on top

- **Behaviour change (live + default path)**:
  - The base strategy for every `starting_weight_source="conviction"` registry entry — including the live book `baseV1_roll20_ewmacov_lam94_tv05` and `default` — now runs the TLT tracker instead of the old regime→direction→table→conviction path; allocation behaviour on these scenarios changes by design. `legacyBase_*` entries (`starting_weight_source="legacy"`) are unchanged and still use the legacy signal table

- **Legacy Relocation & Pipeline Rewire**:
  - Moved `favourable_asset_selection.py` and `base_allocator_engine.py` to `src/legacy/` (the old regime-table modern path); `src/decision/pipeline.py` now calls the tracker, with the old `favourable_assets → base table → conviction` sequence commented out as a rollback safety net per the repo convention
  - The relocated allocators are still exercised directly by `tests/strategy/test_favourable_assets.py` and `test_base_allocator.py` (imports repointed to `src.legacy.*`)

- **Dashboard Benchmark Alignment (`streamlit/home_page_tabs/nav_comparison.py`)**:
  - The TLT/AGG/SHY buy & hold benchmark lines now start at the actual backtest window (`results["date"].min()`) instead of a hardcoded `2014-01-01`, so the benchmarks line up with the scenario NAVs over the same period

- **Tests**:
  - Added `tests/strategy/test_tlt_tracker.py` (state-machine units: confirmation lag, hysteresis band, UP ramp, DOWN buffer, faster exit, macro veto/confirm, data fallback, determinism); updated `tests/strategy/test_pipeline_integration.py` to the tracker pipeline (old regime-table assertions preserved, commented). Full suite green (220 passed)

  ## V 1.12.0

- **New FastAPI Analytics Service (`api/`)** — Phases 0-2 of the React/FastAPI migration (`docs/fastapi_react_migration_spec.md`):
  - Added a read-only REST service that sits between the existing Python analytics core and the browser, **reusing** the existing compute (`src/storage/db_reader.py`, `src/accounting/tearsheet_builder.py`) rather than reimplementing it. Runs alongside Streamlit (does not replace it yet), reading the same `data/database.db`
  - Endpoints under `/api/v1`: `health` (DB-exists gate), `scenarios`, `backtest-results/nav-comparison`, `backtest-results/returns`, `etf-prices`, `etf-prices/stats`. Thin router → service → schema layering; the only server-side arithmetic not already in `src/` (the NAV/price summaries Streamlit computed in-tab) lives in one place, `api/services/summaries.py`
  - Serialization boundary (`api/serialization/frames.py`): a single home for the three JSON hazards — NaN/Inf → `null`, heterogeneous DB dates → ISO `YYYY-MM-DD` (the `backtest_results.date` `00:00:00` vs bare-date split is normalized via `format="mixed"`), and DataFrame/Series → typed payloads. `ORJSONResponse` is kept as a NaN-safety net
  - Config via `pydantic-settings` (`api/config.py`); read-only and imports no secrets/`FRED_API_KEY`. DB path is sourced from `src/storage/paths.py:DB_PATH`; the import-root split (repo-root vs `src/`) is resolved once in `api/_bootstrap.py`

- **New React Analytics SPA (`frontend/`)**:
  - Vite + TypeScript + TanStack Query single-page app mirroring the Streamlit views, with three live tabs: **NAV Comparison** (scenario lines + dashed buy & hold benchmarks + performance summary), **Returns Analysis** (dense daily-return WebGL scatter), and **ETF Prices** (close lines + statistics). The remaining tabs are present but disabled until their phases land
  - Charting: Recharts for the light line/table views (ETF Prices); Plotly for the NAV chart and the WebGL returns scatter. Plotly is `React.lazy`-loaded into a single shared, code-split chunk, so the app shell + tables render immediately and Plotly is fetched once
  - TypeScript types are generated from the live OpenAPI schema (`npm run gen:api`), so the Python ↔ TS contract is enforced at compile time. A `HealthGate` blocks the app until the DB is reachable; an `ErrorBoundary` contains per-view render errors. All `$`/`%` formatting is client-side (`frontend/src/lib/format.ts`) — the API returns raw, machine-usable numbers

- **No engine / trading behaviour change**:
  - Read-only analytics plumbing — no change to the decision/sizing/execution core, no new persisted tables or schema migrations. The new stack only reads what `run_backtest.py` already persisted, so backtest/live behaviour is untouched

- **Tests & dependencies**:
  - Added the `api/tests/` suite (55 passing): `/health`, serialization round-trips (NaN/Inf/date hazards), and per-endpoint shape + reducer unit tests
  - `requirements.txt` gains `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `orjson`; `requirements-dev.txt` gains `httpx` (FastAPI `TestClient`). No change to the `src/` tree
  - Deprecated the historical-grid assertions in `tests/strategy/test_presets.py` (skipped, not deleted, per the repo convention): the persisted scenario registry evolves, so pinning the exact `baseV1_*` names no longer holds after the V1.11.0 base-strategy swap

  ## V 1.13.0

- **Tearsheet view + daily rows (`api/` + `frontend/`)** — Phase 3 of the React/FastAPI migration, the one real compute path:
  - Added `GET /api/v1/tearsheet/{scenario_id}` — serializes `accounting.tearsheet_builder.build_tearsheet` **unchanged** (`api/services/tearsheet.py`): loads the same three frames the Streamlit tab loads, reproduces the regime-match-rate caption, and TTL-caches the result on `(scenario_id, risk_free_rate, periods_per_year)` (deterministic pure function of immutable DB state)
  - `api/serialization/dataclasses.py:tearsheet_to_response` walks the `TearsheetResult` into the response: equity/drawdown/rolling curves → `NamedSeries`, the three summary frames → `TableModel | None` (branching on `.empty`, since the builders return an *empty* frame not `None`), the 26-field metrics → a flat nullable model. Unknown scenario → 404; `build_tearsheet`'s ValueError (empty / missing-column / >1 scenario) → 422
  - Added `GET /api/v1/backtest-results/{scenario_id}/daily` — paginated raw rows (`weights` parsed back to an object via `tearsheet_calculator.parse_weights`)
  - React `TearsheetPage`: a `MetricGrid` of the ~20 meaningful metrics + equity/drawdown/rolling charts + exposure/regime/benchmark tables + a collapsible raw-rows table

- **Volatility, Macro, and Strategies views (`api/` + `frontend/`)** — Phase 4, completing read parity with all six Streamlit views:
  - `GET /api/v1/volatility-features` + `/latest` (Tab 5): per-ticker annualized-vol lines (`rolling_20/60`, `ewma_94/97`, `garch`) + the latest-per-ticker table
  - `GET /api/v1/macro` + `/macro/yield-curve` (Page 6): macro indicator series (each NaN-dropped onto its own monthly axis) + the 10Y/2Y yields and the `gs10 − gs2` spread
  - `GET /api/v1/strategies` (new capability): flattens the live `STRATEGIES` registry (`src/strategy/presets.py`) so the UI can decode the opaque scenario names; the live book is flagged. Read-only introspection — it does not let the UI change the live strategy
  - React `VolatilityPage`, `MacroPage` (the dual-axis ETF-vs-indicator charts), and a new **Strategies** tab (a 7th tab, beyond the six Streamlit views)

- **Charting refinements (`frontend/`)**:
  - The NAV, Returns, and Tearsheet charts now render with Plotly via a reusable `PlotlyLineChart` (secondary y-axis for the rolling vol/Sharpe and the macro dual-axis charts, `fill` for the yield spread), lazy-loaded into a single shared, code-split chunk so Plotly's ~4.5 MB is fetched once. The CJS↔ESM interop (`react-plotly.js` default-importing as `{default}` under Vite) is unwrapped once in `components/charts/plotlyComponent.ts`
  - Removed the per-chart scenario-toggle UI — the Plotly legend itself toggles curves (single-click hide, double-click isolate), reshaped into a compact multi-column legend; full payloads are fetched once and filtered client-side (no refetch on toggle)
  - Hover shows only the curve under the cursor (`hovermode: "closest"`), not every series at once

- **No engine / trading behaviour change**:
  - Read-only analytics plumbing — `build_tearsheet` and all readers are called unchanged; no new persisted tables or schema migrations

- **Tests**: 72 `api/` tests pass (the new tearsheet/daily, volatility, macro, and strategies suites on top of the existing ones); `npm run build` clean with Plotly code-split

  ## V 1.14.0

- **Backtest-from-UI trigger (`api/` + `run_backtest.py`)** — Phase 5 of the React/FastAPI migration: the one *write* path, behind an unchanged two-endpoint contract (§5.1). The read-only stack stays read-only; this is the first thing that writes:
  - `POST /api/v1/jobs/backtest` launches a run (optionally a subset of strategy names) and returns `202` with the job; `GET /api/v1/jobs/{job_id}` polls it. An in-process job registry + a single-slot `ThreadPoolExecutor` (`api/services/jobs.py`) serialize runs so there is only ever **one SQLite writer** — a second trigger while one is active is rejected with `409`; unknown strategy names → `422`. The tearsheet cache is flushed on completion (§5.2). No Celery/Redis — single-analyst, single-node, with a documented upgrade path behind the same two endpoints
  - `run_backtest.py` refactored (behaviour-preserving): `main()`'s body is extracted into a callable `run_backtests(strategy_names=None) -> list[str]` the job worker invokes, and the DB connection is opened per-run (was module-level) so the engine can be triggered repeatedly. `main()` and the `python run_backtest.py` entry point are unchanged — running the whole registry is the same path as before
  - React: a "Run backtest" panel on the Strategies page (`useMutation` to trigger, poll via TanStack Query `refetchInterval` until `done`/`error`) that invalidates the analytics queries on completion, so every view picks up the fresh data

- **Tests**: 77 `api/` tests pass — the job lifecycle / 202 / 409 / 422 / error / 404 suite runs against a stubbed runner, so no real (minutes-long) backtest runs in CI; `npm run build` clean

  ## V 1.15.0

- **Streamlit retired to legacy; FastAPI + React is the dashboard (Phase 6)** — the parity sign-off that closes the React/FastAPI migration (`docs/fastapi_react_migration_spec.md`):
  - The React SPA + FastAPI service reached parity with all six Streamlit views in V1.13.0 and went beyond them (a Strategies registry tab and the V1.14.0 backtest-from-UI trigger). It is now the documented way to run the dashboard
  - Added a **"Running the App"** section to this README: the two-process dev model (`uvicorn api.main:app` + `npm --prefix frontend run dev`), how to trigger a backtest, and how to launch the legacy Streamlit app
  - The `streamlit/` app is **retired but kept** (repo convention: comment/retire, don't delete) — still launchable via `streamlit run streamlit/app.py` against the same `data/database.db`, but frozen: new analytics land only in the React stack. No `streamlit/` files were changed or removed, and nothing launches Streamlit automatically (it was always a manual `streamlit run`)
  - Documentation / run-instructions only — no code or engine change

  ## V 1.15.1

- **Backtest jobs: subprocess execution, live progress, and cancellation (`api/` + `run_backtest.py` + `frontend/`)** — refining the V1.14.0 trigger:
  - The backtest now runs in a **subprocess** (`api/backtest_worker.py`, spawned by `api/services/jobs.py`) instead of an API thread, so the CPU-bound run no longer GIL-starves the event loop — the dashboard stays responsive while a backtest runs (a full ~45-min registry run previously made the UI laggy)
  - **Live progress**: `run_backtests` gained an optional `on_progress(completed, total, strategy)` callback (additive / behaviour-preserving — `None` keeps it identical). The worker streams `@@JOB@@`-prefixed JSON over the subprocess's stdout, which the service parses into new `progress_current` / `progress_total` / `progress_strategy` fields on `JobStatus`; the Strategies-tab "Run backtest" panel renders a per-strategy progress bar
  - **Cancellation**: `POST /api/v1/jobs/{job_id}/cancel` terminates the subprocess (new `cancelled` status), surfaced as a "Cancel" button while a run is in flight. Safe by construction — `run_backtests` only commits at the very end, so a cancelled run rolls back to the DB's pre-run state with no partial data
  - Tests drive a fast fake worker (overriding the spawn command), so the real spawn / stream / terminate machinery is exercised without a minutes-long backtest — **78 `api/` tests pass**; `npm run build` clean

  ## V 1.15.2

- **Returns Analysis redesigned as a diagnostic tool (`api/` + `frontend/`)** — reworks the dense all-scenario returns scatter into a focused daily-return diagnostic (`docs/returns_analysis_diagnostic_redesign_spec.md`). Read-only; no engine or trading change:
  - New `api/services/returns_diagnostics.py` + `GET /api/v1/backtest-results/returns-diagnostic`: parses scenario ids into readable labels (`baseV1_roll20_ewmacov_lam94_tv03` → "Base / EWMA λ94 / TV 3%") and metadata, enriches returns with weights / primary holding / regime context (left-joined from `get_backtest_regime_trace` on `["date","scenario_id"]`, the same key `tearsheet.py` uses), and builds the worst-returns / best-returns / largest-scenario-dispersion tables. Pure transforms, unit-tested in `api/tests/test_returns_diagnostics.py`
  - **Fetch-all-once model**: the endpoint ships the entire scenario grid in a single payload, so showing/hiding a scenario is a pure client-side Plotly legend toggle (click to show/hide, double-click to isolate) with **no refetch** — `default_visible` names the ~3 drawn on load, the rest start `legendonly`. Family / volatility-method / target-vol controls narrow which curves render; date-range presets (Full / COVID / 2022 rate shock / Last 3y / Custom) and the six return-filter modes are server params (cached per combination). The boxplot mirrors the visible curves
  - `GET /api/v1/backtest-results/returns-diagnostic/point`: rich single-point detail fetched on demand for the click-drilldown panel, so the main scatter payload stays lean (date + return only)
  - React: `ReturnsScatter` rebuilt (React-owned legend visibility, ±1%/±2% reference lines, on-click selection), new `ReturnsBoxplot`, `ReturnsPage` rewritten with the controls + diagnostic tables, and `useReturnsDiagnostic` / `useReturnsPointDetail` hooks. The legacy `/returns` endpoint, service, and hook are kept (superseded, not removed)
  - **Performance**: vectorized the dispersion aggregation (was a Python loop over ~4k dates) and the return rounding, enrich only the ~40 rows that land in the tables (not the full ~86k-row grid), and return the large payload via `ORJSONResponse` to skip per-element Pydantic validation — the full-grid response dropped from ~8.7s to ~2.4s (`response_model` still drives the OpenAPI schema/types)

- **Dashboard typography (`frontend/`)**:
  - Added the Metaluna fonts (`@font-face` in `src/index.css`, served from `public/`): the "Scenario Testing Dashboard" title renders in Metaluna Inline, all other UI text in Metaluna Medium

- **Tests**: **107 `api/` tests pass** (29 new returns-diagnostic tests on top of the existing suites); `npm run build` clean with the Returns charts code-split into the shared Plotly chunk

  ## V 1.15.3

- **Dashboard typography + UI polish (`frontend/`)** — presentation only, no behaviour change:
  - **Play font for tabular data**: table body cells (headers excluded) and the tearsheet metric-card numeric values now render in Play (`@font-face` in `src/index.css`, served from `public/Play/`), exposed via a `--font-data` CSS variable so the family lives in one place. The metric-card values were also dropped from semibold to regular weight
  - **Form controls inherit the UI font**: a small reset (`button` / `select` / `input` / `textarea` → `font-family: inherit`) so the tab buttons and the Returns Analysis controls use Metaluna Medium like the rest — `<button>`/`<select>` don't inherit `font-family` by default
  - **Fluid layout**: the app shell is now `maxWidth: min(2000px, 95vw)` (was a fixed 1200px), so the dashboard — and the wide diagnostic tables especially — use more of the screen as the window widens
  - **Returns scatter reference lines** are now bright red (0% solid + thicker, ±1%/±2% dotted) so they stand out against the points

  ## V 1.16.0

- **Colour theme toggle (`frontend/`)** — a 3-mode light / dark / high-contrast theme switch; colour-only, no layout, typography, or logic change:
  - **Rotating toggle control** in the header top-right (`src/components/ThemeToggle.tsx`): three icons on a circle 120° apart — sun (light), moon (dark), star (high contrast). The active mode's icon sits at the top; clicking one of the other two brings it to the top by rotating the **shorter way**, so the ring spins clockwise or counter-clockwise depending on which icon you click (right icon → CCW, left icon → CW). Rotation is tracked as a continuous accumulating value so each move animates the minimal arc; glyphs counter-rotate to stay upright
  - **Theme state** (`src/theme/ThemeContext.tsx`): `ThemeProvider` writes the mode to `data-theme` on `<html>` and persists it to `localStorage`; wraps the app above the query client in `main.tsx`
  - **CSS-variable palettes** (`src/index.css`): every chrome colour is routed through semantic tokens (`--text*`, `--surface*`, `--border*`, `--accent`, `--on-accent`, `--danger*`, `--success`) with three palettes keyed off `:root[data-theme=...]`. The **light palette values are the exact hex literals used before**, so light mode is pixel-identical to the prior design. High-contrast mode uses electric-blue (`#00b3ff`) text on black. All inline hardcoded hex across the 15 page/component files was swapped to `var(--token)`
  - **Chart canvas theming** (`src/theme/chartTheme.ts` + the five chart components): Plotly and Recharts now read `useChartColors()` (re-renders on mode change) for font / grid / axis / hover / modebar colours; the canvas itself is transparent (`paper_bgcolor`/`plot_bgcolor`) so charts inherit the themed page/card background. **Data-trace colours stay constant** across modes (series identity — TLT/AGG/SHY, the scenario palette, the returns reference line — is not themed)

- **Charts use header labels instead of y-axis titles (`frontend/`)**:
  - The rotated y-axis title was removed from every chart and replaced with a centred header above the plot (`src/components/charts/ChartHeader.tsx`). Single-axis charts show their old `yLabel`; dual-axis charts join both labels (e.g. "Yield (%) · Spread (%)"). The x-axis "Date" title and all tick formatting ($/%) are unchanged

- **Build**: `npm run build` clean (`tsc -b` + Vite); the new theme module and chart helpers code-split alongside the existing chunks

  ## V 1.16.1

- **Tooltips + table polish (`frontend/`)** — presentation only, no behaviour change:
  - **Reusable info tooltip** (`src/components/InfoTooltip.tsx`): a small "ⓘ" trigger that reveals an explanatory panel on hover or keyboard focus, themed via the CSS variable tokens so it reads in all three colour modes
  - **Returns Analysis** — the descriptive blurb under the title was moved into an info tooltip on the title; the **Return Distribution by Scenario** section gained a detailed tooltip explaining how to read the box plot (median / IQR box / whiskers / outliers and how to compare scenarios)
  - **Tearsheet benchmark summary table**: the verbose `benchmark_*` column headers now display as "Total Return" / "CAGR" / "Volatility" / "Max Drawdown" (display-only via a header-label map; sort + `$`/`%` formatting still key off the raw column names) so the table stops overflowing
  - **Tearsheet summary line**: the `scenario | dates | regime match rate` separators are now spaced out via a small `Separator` element (tinted with `--text-faint`) instead of bare pipes

  ## V 1.17.0

- **Macro data interpretability — correct & redesign the ETFs-vs-Macro dashboard** (`docs/macro_data_interpretability.md`, all 5 phases). Read-only analytics; **no strategy / decision / sizing / backtest change**. The macro feature derivations are single-sourced (see the engine refactor below) and every pure transform is unit-tested.

- **Single source of truth for macro derivations (`src/signals_macro/macro_features.py`, new)** — the base formulas (`cpi_yoy`, `core_cpi_yoy`, `yield_curve`/`curve_spread`, `real_policy_rate`) previously duplicated in `macro_signal_engine.py` and `fetch_macro_data.py` now live in one pandas-only module that both import (old inline formulas commented out as a rollback safety net). Behaviour is byte-identical — locked by `tests/strategy/test_signals.py` (engine columns) and `test_macro_features.py` (equality pin); no existing test modified.

- **Phase 1 — data correctness (`api/` + `frontend/`)**: the headline mislabel is fixed at the source. The API now serves derived series (`cpi_yoy`, momentum/change features, real policy rate, yield-curve changes) alongside the raw columns, each with a `meta` carrying its true `source`/`unit`/`frequency`. `MacroPage` plots **CPI YoY** (a decimal fraction rendered `.1%`), not the CPI index mislabelled as YoY; **CFNAI** is named correctly (neutral 0) instead of "PMI"; ETF prices are labelled **Adjusted Close**. Units vocabulary: `level` / `pct` / `pct_frac` / `pp`.

- **Phase 2 — yield-curve interpretation**: `classify_curve_regime` (bull/bear × steepening/flattening + mixed) over the 2y/10y changes; endpoint 11 also returns the curve-regime series, inversion intervals, and the current regime. React adds inversion shading + a current-regime badge + interpretation note. Categorical-over-time series use a new `CategoricalSeries` wire model (numeric code + label + `categories` map) so the dense numeric series never pay for a per-point label.

- **Phase 3 — snapshot cards + ETF/macro explorer + display modes**: `GET /api/v1/macro/snapshot` returns latest-reading cards (each with its **own** observation date, 3-month change/direction, unit, stale flag). The six fixed ETF×macro charts are replaced by an **Explorer** (ETF / macro-indicator / date-range selectors) with **Dual axis**, **Indexed to 100**, and **Scatter vs forward return** display modes.

- **Phase 4 — macro-regime classifier + timeline**: `classify_macro_regime` → five transparent, **dashboard-only** regimes (Stable Growth / Inflationary Tightening / Disinflationary Slowdown / Stagflation Risk / Easing Transition), explicitly distinct from the engine's allocation regimes. `GET /api/v1/macro/regime-timeline` returns the regime ribbon + an **engine comparison overlay** (the persisted `macro_supports_duration` signal) + a legend of per-regime bond-preference *priors*. React shades an ETF chart by regime with an overlay switch (dashboard ⇄ engine) and a colour legend.

- **Phase 5 — conditional forward returns**: `GET /api/v1/macro/conditional-returns` → a regime × ETF `TableModel` of forward-return statistics (1/3/6/12-month mean, 3M hit rate / median, observation count), with **look-ahead discipline** (macro lagged to a reference-month-end + 1 month availability proxy; forward returns measured strictly after via `merge_asof`) and honesty caveats (descriptive-not-predictive, overlapping-horizon non-independence, thin-regime flags). `GET /api/v1/macro/forward-return-scatter` powers the Explorer's scatter mode (Δ-macro vs subsequent ETF return).

- **Accepted debt**: the macro availability lag is a flat "reference month-end + 1 month" proxy (not point-in-time vintage data), kept behind `macro_availability_dates` to be superseded by a future forecasting/nowcasting system.

- **Tests**: **+30 macro-features unit tests** and **+19 macro API tests** (regimes, forward returns, look-ahead, strict JSON, units). Full suites green (`pytest -m "not slow"` + `api/tests`); `npm run build` clean with the new scatter chart code-split into the shared Plotly chunk.

  ## V 1.18.0

- **Volatility Features diagnostic dashboard** (`docs/vol_features_plan.md`, Phases 0–6; React/FastAPI). The Tab 5 view grows from a raw five-estimator comparison into an interpretable diagnostic surface. Read-only analytics — **no strategy / sizing / weight / backtest change**; Streamlit untouched. Every derived feature is point-in-time on the already-one-day-lagged surface (never re-shifted), isolated by `config_key`, and cached per the plan's §7 keys (data-version + threshold-config versions so a stale row or a threshold change both invalidate). New pure, UI-agnostic modules under `src/volatility/`, each fully unit-tested under `tests/volatility/` with `lookahead`-marked guards.

- **Phase 0 — data contract (`src/volatility/audit.py`, `constants.py`)**: `validate_volatility_surface` (non-fatal warnings: duplicate keys, negatives, non-monotonic dates, mixed `config_key`, decimals-not-percent) and `normalize_volatility_surface` (single-`config_key`, canonical column order, warm-up `NaN`s preserved). Canonical estimator names (`rolling_20`/`rolling_60`/`ewma_94`/`ewma_97`/`garch`) single-sourced; `surface_data_version` freshness token. Read-only `GET /api/v1/volatility-features/audit`; contract documented in `docs/volatility_data_contract.md`.

- **Phase 1 — historical percentiles (`percentiles.py`)**: point-in-time `compute_rolling_percentile` (vectorised `rolling/expanding.rank`, `method="average"`, inclusive of the as-of observation) over selectable 3Y/5Y/10Y/Full windows, plus a Low/Normal/Elevated/High/Extreme level classifier (upper-edge rule). `GET …/context` (latest vol + percentile + level + as-of/`t-1` dates) and `GET …/percentile` (the 0–100% line with 20/60/80/95 guides). A constant window resolves to `(k+1)/(2k)` — **not** 1.0 — so a flat series reads mid-distribution, not spuriously Extreme (spec corrected to match).

- **Phase 2 — direction + term ratio (`direction.py`)**: 5d/20d **relative** changes and the 20D/60D ratio (`rolling_20/rolling_60`, division-safe), classified Rising/Falling/Stable and Expansion/Balanced/Contraction. `GET …/derived` serves the ratio and change views; the UI carries the required methodology note that the overlapping-window ratio is mechanically mean-reverting and its bands are descriptive, not statistical.

- **Phase 3 — unified diagnostic state (`states.py`)**: a deterministic ordered-precedence classifier (Unknown → Shock → Stress Expansion → Normalisation → Persistent Stress → Early Expansion → Calm) producing **both** an instantaneous and a persistence-**confirmed** state (debounced `confirmation_days`, default 10 — a ~2-week regime cadence, ~6 changes/yr rather than ~14 at 3 days) so the headline never flickers on a single-day Extreme. Deterministic template explanation; `GET …/state-table` for all assets. Card shows the confirmed state with `now:` instantaneous when they differ.

- **Phase 4 — estimator agreement (`agreement.py`)**: relative dispersion `(max−min)/median` **and** an absolute-spread floor — `Low` agreement requires **both** the relative breach and `absolute_spread > low_agreement_absolute_floor`, so SHY's ~1–2% vol can't read as false disagreement. `GET …/agreement` returns the summary + a per-estimator comparison panel (current vol, percentile, **absolute pp** and **relative %** diff vs median — the old ambiguous "diff vs median" split in two); a `dispersion` chart view added.

- **Phase 5 — price/volatility context (`price_context.py`)**: as-of-`t-1` adjusted-price direction (`prices.shift(1).pct_change(h)`) joined with volatility direction into Adverse Shock / Positive Volatility Expansion / Stable Positive Trend / Controlled Decline / Quiet (the same `t-1` information boundary as the vol surface). **Yield enrichment deliberately deferred** — `gs10`/`gs2` are monthly-ffilled FRED data, so a daily "20-day yield change" would be a misleading staircase.

- **Phase 6 — unified typed chart + shading + markers (`transitions.py`)**: one `GET …/chart` endpoint serves all five views (volatility | percentile | ratio | change | dispersion) as typed `VolatilityChartResponse` (series + `unit` + `reference_lines` + `state_ranges` + `transitions`) — **no `go.Figure` built server-side**. `build_state_ranges` (contiguous confirmed-state bands) and `detect_persistent_state_transitions` (one marker per confirmed change, per-kind `cooldown_days`-gated). React assembles the Plotly traces from the typed payload; `PlotlyLineChart` gained vertical transition `markers`; the page adds **State shading** (notable states only; a colour key renders beneath the chart) and **Transition markers** toggles (markers default off — the diagnostic state changes often, so full-history markers are opt-in).

- **Frontend (`frontend/src/pages/VolatilityPage.tsx`)**: the single diagnostic chart is now driven by `/chart` across all views; a state/context card (level, direction, diagnostic state, estimator agreement, price/vol context), an estimator-comparison panel, and an all-asset confirmed-state table supplement — never replace — the raw latest-values table. Reference estimator + window are selectable. Typed client regenerated (`npm run gen:api`).

- **Tests**: **+115 volatility unit/lookahead tests** (`tests/volatility/`) and **+22 volatility API tests** (`api/tests/test_volatility.py`, 27 total) covering every state, the agreement floor, the percentile constant-series lock, price-context look-ahead, and chart units/ranges/transitions per view. Full backend suite green (512 passed / 5 skipped); `npm run build` clean (Plotly stays code-split).

  ## V 1.19.0

- **Volatility Features diagnostic dashboard — Phases 7–10 (`docs/vol_features_plan.md`; React/FastAPI)**. Completes the plan (PR0–PR10): cross-asset relative volatility, estimate stability, historical signal outcomes (incl. combined-condition signals + a forward-return boxplot), and the passive strategy-integration snapshot interface. Same contract as Phases 0–6 — **no strategy / sizing / weight / backtest change**, Streamlit untouched; every derived feature point-in-time on the already-one-day-lagged surface (never re-shifted), isolated by `config_key`, cached per the plan's §7 keys; new pure modules under `src/volatility/`, each `lookahead`-tested under `tests/volatility/`.

- **Phase 7 — cross-asset relative volatility (`relative.py`)**: point-in-time TLT/AGG, TLT/SHY, AGG/SHY vol ratios (division-safe) with their own historical percentiles, plus an all-asset risk ranking. `GET …/cross-asset` and `…/cross-asset/ratio-series`. **Monitor only** — the UI carries the required caveat that a duration-driven ratio's high percentile is a single-path, trend-laden reading, not a tradable signal.

- **Phase 8 — estimate stability (`stability.py`)**: `compute_volatility_of_volatility` (20D std of daily changes in the annualised estimate) surfaced as a **percentile-first** Stable/Changing/Unstable status — the raw value is muddy units, kept to a labelled details/methodology line. `GET …/stability`; a `vov` chart view; stability columns added to the all-asset table.

- **Phase 9 — historical signal outcomes (`outcomes.py`)**: forward returns / drawdowns / hit-rate by confirmed state over 1M/3M/6M, with **non-overlapping sampling as the honest default** ("all observations" an explicit, flagged override) and hard minimum-sample gates (Insufficient < 5 / Anecdotal 5–9 / Low 10–19 / full ≥ 20) that suppress stats for thin samples. Strict look-ahead split: state from the lagged surface (as-of `t`), forward returns from **unlagged** prices strictly after `t`, joined one-to-one (`validate="one_to_one"` guards row multiplication). `GET …/outcomes`, `…/outcomes/conditions`, `…/outcomes/distribution`.

- **Phase 9 — combined-condition signals + boxplot**: six point-in-time conditions (vol rising + price falling / rising, vol falling after High/Extreme, 20D/60D in expansion, estimator agreement Low, and the cross-asset TLT/AGG relative-vol > 90th pct) analysed independently with the same gates; the cross-asset condition keys on the **TLT/AGG** freshness token so a TLT/AGG-only refresh invalidates another ticker's cached conditions. A forward-return **boxplot by state** via a shared `BaseBoxplot` (now backing both `OutcomeBoxplot` and `ReturnsBoxplot`). On the page, the diagnostic chart is the centrepiece — the volatility-state and risk-estimate-stability cards moved below it.

- **Phase 10 — passive strategy-integration snapshot (`snapshot.py`)**: `AssetVolatilitySignalSnapshot` / `CrossAssetVolatilitySnapshot` frozen dataclasses — one stable, typed, point-in-time snapshot of the Phase 1–8 diagnostics with **full reproducibility metadata** (config + threshold-config versions, `minimum_history`, and both `as_of_date` (t) / `information_through_date` (t-1)). A thin `VolatilitySignalSnapshotProvider` over the existing `VolatilityFeatureSurface.get_ticker_snapshot` (the **single** as-of path; diagnostics computed from the trailing `date ≤ as_of` history). `GET …/snapshot` (+ `as_of`) and `…/snapshot/cross-asset`; a **"Strategy signal snapshot (passive)"** page panel, clearly labelled not wired to allocation. Future uses (sizing, risk overlays, allocation context) documented but explicitly **not** implemented.

- **Reuse / cleanup (no behaviour change)**: extracted the per-row feature orchestration into the pure `src/volatility/feature_frame.py` `build_ticker_feature_frame`; the API service's `_features_frame` now delegates to it (keeping its TTL-cached percentile), so the dashboard and the snapshot share one source of thresholds. The Phase 9 outcome/condition tables share one `_aggregate_group` (uniform gating, no synthetic-frame round-trip); the three outcome endpoints share `_forward_outcome_frame` / `_confirmed_state_frame`; the TLT/AGG ratio percentile is cached and shared with Phase 7.

- **Tests**: **+volatility unit/lookahead tests** for outcomes, relative, stability, snapshot, combined conditions and the boxplot/condition tables (incl. truncation/no-future-leak and many-to-many-join guards), plus snapshot + outcome API tests. Volatility + API suites green (**245 passed**); repo-wide `lookahead`/`determinism` markers green (**58 passed**); `npm run build` clean (boxplots code-split, shared `BaseBoxplot`).

  ## V 1.19.1

- **Volatility Features dashboard — readability polish (`frontend/src/pages/VolatilityPage.tsx`; no behaviour change)**:
  - Reworked the volatility-state + risk-estimate-stability cards into a single uniform "SnapCard" grid (matching the Macro "Latest readings" tiles), folding the standalone stability card's two fields into it.
  - Converted long explanatory paragraphs to hover `InfoTooltip`s (the Metaluna-Medium-styled panel) on the Cross-asset risk, Historical signal outcomes, Combined-condition signals, and the outcomes disclaimer/sampling-gates headers; standardised every info button to the shared 17px style.
  - Spaced the two Cross-asset risk tables into a 2-column grid to use the available width.

- **Strategy signal snapshot panel removed from the UI (`VolatilityPage.tsx`)**:
  - The passive snapshot section added more confusion than value, so its render + state/hook are commented out (kept for easy restore); the `/snapshot` API and `src/volatility/snapshot.py` are untouched.

- **High-contrast regime shading + chart curve colours (`VolatilityPage.tsx`, `MacroPage.tsx`, `OutcomeBoxplot.tsx`, `charts/PlotlyLineChart.tsx`, `charts/BaseBoxplot.tsx`; theme-only)**:
  - High-contrast mode now uses vivid, maximally-distinct neon fills for the annualised-volatility chart's confirmed-state shading and the Macro Regime Timeline bands (blue avoided — the contrast theme's axes are already electric blue); other modes keep the original subtle palette.
  - Calm vs Unknown are now visually distinct in both the state shading and the forward-return boxplot.
  - Primary chart curve / box colour is cyan (`#06b6d4`) in dark + high-contrast modes and the original Plotly blue (`#1f77b4`) in light mode, across the Tearsheet, Volatility, ETFs-vs-Macro line charts and the Returns Analysis distribution boxplot; the rest of the palette and all other chart styling are unchanged.

  ## V 1.20.0

- **Select the live strategy from the dashboard (`src/strategy/presets.py`, `api/.../strategies.py`, `frontend/.../StrategiesPage.tsx`)**:
  - The Strategies tab's ★ is now interactive — click any row's ☆ to choose which registry entry the live run (`main.py` → `live_strategy()`) trades. A runtime override is persisted to `data/live_strategy.json` (gitignored, like the DB) and read by both the API and the live run; the `LIVE_STRATEGY` constant remains the built-in default and a **Reset to default** button clears the override.
  - `src/strategy/presets.py` gains `live_strategy_override` / `effective_live_strategy_name` / `set_live_strategy_override` / `clear_live_strategy_override`; `live_strategy()` now honours the override, falling back to the constant. The no-override path is behaviour-preserving (effective name == constant). Malformed override files (bad JSON, non-object, non-string/unknown name) are treated as "no override" rather than crashing the live run.
  - API: `GET /strategies` now also returns `default_strategy` + `is_overridden`; new `POST /strategies/live` (unknown name → 422) and `POST /strategies/live/reset`. React adds `useSetLiveStrategy` / `useResetLiveStrategy` (cache-seeding mutations); the ☆ glyph and Reset button text follow the theme (white on dark, electric blue on high-contrast).

- **Tests**: `api/tests/test_strategies.py` covers set/reset round-trip, unknown-name 422, and a parametrized malformed-override fallback, isolated via a monkeypatched `_OVERRIDE_PATH` temp file so the real `data/live_strategy.json` is never touched. Full suite green (root **441 passed / 5 skipped**; `api/tests` **182 passed**). Note: CI's `pytest -q` (`testpaths = tests`) does not collect `api/tests`, so these run locally via `python -m pytest api/tests`.

  ## V 1.20.1

- **Frontend UX/maintainability spec + Phase 1 theme-token consolidation (`docs/frontend_ux_improvements_spec.md`; no behaviour change)**:
  - Added `docs/frontend_ux_improvements_spec.md` — a UX review scoped into six small, independently-shippable phases (token consolidation, shared stat primitive, tab/selection persistence, Volatility page hierarchy, affordances/a11y, dead-code/loading polish).
  - **Phase 1 (this release):** relocated hardcoded chart/regime/star colours into the theme layer with **byte-identical rendered values in every mode** (pure refactor). `theme/chartTheme.ts` now defines a per-mode trace `colorway` (cyan primary on dark/contrast, Plotly blue on light) consumed by `PlotlyLineChart` + `BaseBoxplot`; new CSS tokens `--star-live` / `--star-empty` / `--control-emphasis-text` in `index.css` replace the per-mode ternaries in `StrategiesPage.tsx`; and a new `theme/regimeColors.ts` is the single home for the volatility confirmed-state shading (`volStateBandColor`), the forward-return boxplot fills (`volStateBoxColor`), and the macro regime maps (`regimeRgbMap` + `INVERSION_BAND`) — removing the duplicated palettes from `VolatilityPage.tsx` and `MacroPage.tsx`.
  - Deferred (out of Phase 1 scope): the diagnostic-state **badge** pill colours and the Recharts ETF-prices palette (`SeriesLineChart`) — both pre-existing and constant across modes. `npm run build` clean.

  ## V 1.20.2

- **Frontend UX Phase 2 — shared labelled-value primitive (`frontend/src/components/StatCard.tsx`; no behaviour change)**:
  - Added `StatCard` + `StatGrid` — one card-tile primitive (card shell, uppercase label header, tabular value) with `info` / `headerRight` / `value` / `children` / `footer` slots, replacing two near-duplicate per-page implementations.
  - Migrated the Volatility state grid (the former `SnapCard`, incl. the Level/Stability badge cards and info tooltips) and the Macro "Latest readings" tiles (the former `SnapshotCardTile`, with its stale tag + 3m-change/as-of footer) onto it. Rendered output is byte-identical in all three themes; the per-page card markup is removed.
  - Deferred (spec-sanctioned): the Tearsheet `MetricGrid` migration (differently-shaped tile). `tsc -b` + `npm run build` clean.

  ## V 1.21.0

- **Frontend UX Phase 3 — URL-synced tab & selections (`frontend/src/hooks/useUrlState.ts`)**:
  - Views are now refresh-safe, bookmarkable, and shareable. New `useUrlState` hook syncs a discrete selection to a URL query param via `history.replaceState` (no router dependency, no history-stack spam): reads once on mount, omits the default from the URL for clean links, and falls back to the default for unknown/garbage values (optional `allowed` validation). Namespaced keys coexist (each write edits only its own param).
  - Adopted for the **active tab** (`App.tsx` → `?tab=`, validated vs `TABS`), the **Volatility** page (`?volTicker` / `?volEstimator` / `?volWindow` / `?volView`), and the **ETFs-vs-Macro explorer** (`?macroEtf` / `?macroIndicator` / `?macroRange` / `?macroMode` / `?macroHorizon`). `activeTicker` now falls back when an out-of-range ticker arrives via the URL.
  - Pattern established for incremental adoption; other pages and the regime-timeline / conditional-returns selectors deferred. `tsc -b` + `npm run build` clean.

  ## V 1.21.1

- **Frontend UX Phase 4 — Volatility page information hierarchy (`frontend/src/pages/VolatilityPage.tsx`)**:
  - Replaced the long single-scroll layout with progressive disclosure. The diagnostic chart + state/context card stay always-visible at the top (the centrepiece); the analytical tables below are now grouped behind an in-page sub-tab bar showing **one section at a time**: *Estimators & State* (estimator comparison + states table), *Cross-asset* (relative-vol tables + pair ratio chart), *Historical outcomes* (the outcomes table, boxplot + combined conditions), and *Latest values* (raw table).
  - The active sub-section is URL-synced via the Phase 3 hook (`?volSection=`, validated, default *Estimators & State*), so it's refresh-safe and shareable. **Display-only:** nothing is removed (every table/chart is still reachable), all data hooks still run unconditionally so switching sections does not refetch or change any computed value. `tsc -b` + `npm run build` clean.

  ## V 1.21.2

- **Frontend UX Phase 5 — interaction affordances & accessibility (`frontend/src/App.tsx`, `index.css`, no behaviour change)**:
  - **Tab nav a11y:** the header tabs are now a proper ARIA tablist — `role="tablist"`/`role="tab"` + `aria-selected`, roving `tabIndex`, and a keyboard model (←/→/↑/↓ move + activate with wrap, Home/End jump to first/last, focus follows); `<main>` is the labelled `role="tabpanel"`.
  - **Visible focus:** a themed `:focus-visible` outline for buttons/tabs/selects/inputs/links (specificity-0 `:where()`), restoring a keyboard focus indicator on custom-styled controls.
  - **Affordances:** the Strategies live-star gains an `.icon-button` hover background; a subtle opt-in `legendHint` on `PlotlyLineChart` ("click a legend entry to show/hide a series") is enabled on the Tearsheet Rolling Vol & Sharpe chart (the multi-series chart with no other toggle UI). `InfoTooltip` triggers were already focus-reachable. `tsc -b` + `npm run build` clean.

  ## V 1.21.3

- **Frontend UX Phase 6 — loading states & cleanup (`frontend/src/App.tsx`, `frontend/src/components/Skeleton.tsx`, `src/index.css`; no behaviour change)**:

  - **Dead-code cleanup:** removed the now-unreachable disabled-tab plumbing from `App.tsx` — including `ENABLED_TABS`, disabled/not-allowed render branches, and the unused `ComingSoon` component — now that all seven tabs ship. The tab render switch now falls back directly to `StrategiesPage`, and the keyboard handler iterates over `TABS` directly.
  - **Stale documentation cleanup:** updated the outdated “phases land later” docstring so the code comments match the current shipped navigation structure.
  - **Loading skeletons:** added reusable `ChartSkeleton` and `TableSkeleton` components with a subtle `.skeleton` pulse animation, plus a `prefers-reduced-motion` opt-out for accessibility.
  - **Volatility page loading states:** the main diagnostic chart now shows a `ChartSkeleton` during both query-loading and lazy-Suspense fallback states. Estimator-comparison and Volatility-states tables now show `TableSkeleton` placeholders while loading.
  - **Tearsheet loading states:** page-load now uses a `TearsheetSkeleton` with a metric-strip placeholder and two chart placeholders; chart-level lazy fallbacks use `ChartSkeleton`.
  *\- **Scope control:** smaller and secondary loading states remain as plain text intentionally, avoiding skeleton overuse while improving perceived responsiveness on the heaviest pages.

  ## V 1.21.4

- **Bugfix — backtest job orphaned on tab switch (`frontend/src/pages/StrategiesPage.tsx`, `frontend/src/api/hooks.ts`)**:
  - Previously, clicking **Run backtest** then leaving the Strategies tab unmounted `BacktestRunner`, dropping its local `jobId`; on return the progress bar + **Cancel** button were gone even though the run continued server-side (holding the SQLite write lock until it finished, blocking reads with "database is locked"). The in-flight job could no longer be cancelled from the UI.
  - Added a `useJobs()` hook over the existing `GET /jobs` registry; `BacktestRunner` now re-attaches on mount to any `queued`/`running` job, restoring its progress + Cancel. Only active jobs are re-adopted (a finished job won't resurface a stale "done" banner). No backend change.