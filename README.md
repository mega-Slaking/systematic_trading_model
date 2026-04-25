# Project Overview
## Current Version: V 1.7.2

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