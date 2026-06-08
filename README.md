# Project Overview
## Current Version: V 1.10.0
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

# Testing

A `pytest` suite lives under `tests/` (see `tests/TEST_PLAN.md` for the full blueprint and coverage map).

- Run everything: `python -m pytest`
- Fast loop (skips the slow GARCH fit and backtest e2e): `python -m pytest -m "not slow"`

It runs automatically in two places:
- **CI** — GitHub Actions (`.github/workflows/tests.yml`) on every push to `main`/`dev` and on pull requests.
- **Pre-commit** — a local hook runs the fast suite before each commit. Enable once with `pip install -r requirements-dev.txt` then `pre-commit install`.

# Expected Timeline:
### V 1.x.x - Measurement and Execution Realism
#### V 1.2.0
- Full Analytics Dashboard
- NAV, returns, drawdowns, exposure history
- Decision logs and regime annotations
- Foundation for performance attribution
#### V 1.3.0
- Transaction cost modeling
- Slippage assumptions
- Explicit trade logs
- Cash-aware accounting reflected in analytics
#### V 1.4.0
- Transition from single-asset switching to multi-position holding
- Explicit tracking of cash and multiple assets
- Portfolio marked-to-market by individual holdings
- Rebalancing via position deltas rather than full liquidation
### V 2.x.x - Exposure Control
#### V 2.4.0
- Partial allocation of capital (Long only)
- Capital can be split across multiple bond ETFs
- Weights-based decisions (instead of binary asset selection)
- Cash treated as a first-class allocation
- Exposure history and contribution analytics
#### V 2.5.0
- Position sizing logic
- Separation of signal direction from exposure magnitude
- Volatility-aware sizing
- Conviction-based scaling
- Maximum position caps
#### V 2.6.0
- Hard portfolio constraints (max drawdown, exposure caps, volatility limits)
- Risk overrides and forced de-risking
- Risk events annotated in analytics
### V 3.x.x - Long-Short Capability
#### V 3.6.0
- Support for negative weights and short positions
- Net vs gross exposure tracking
- Margin-aware accounting
- Short exposure limits and forced liquidation rules
#### V 3.7.0
- Borrow / financing cost modeling
- Time-dependent short carry
- Short-side performance attribution
### V 4.x.x - Learning and Adaptation
#### V 4.7.0
- Feature engineering from price, macro, regime, and risk data
- Walk-forward validated ML models
- ML used as an allocator / confidence modulator, not a price predictor
- ML outputs feed into sizing and allocation layers (never execution)

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