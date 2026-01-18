# Project Overview
## V 1.1.0

This project implements a systematic, rule-based trading strategy designed to rotate between three U.S. Treasury–focused bond ETFs:

TLT — Long-duration Treasuries

AGG — Broad U.S. bond market

SHY — Short-duration “cash-like” Treasuries

The strategy uses a hybrid signaling model that combines:

Price-based trend / momentum indicators (short horizon; faster reaction)

Macro-based direction + acceleration filters (slow horizon; validation layer)

The system aims to participate in bond rallies, reduce exposure during tightening cycles, and avoid duration risk in unstable macro environments — without needing predictive forecasting or assumptions about future policy decisions.


# Goal of the Strategy

The core goal is:

Rotate into assets that benefit from the current monetary regime and exit duration exposure when macro instability exceeds reward.

Put simply:

If disinflation and weakening growth → duration benefits → TLT

If macro stable and non-accelerating → broad bond allocation → AGG

If inflation accelerating or uncertainty rising → reduce duration → SHY

The strategy strives to be:

Simple enough to understand

Systematic enough to avoid emotion

Flexible enough to evolve

Based on economic reasoning, not hindsight heuristics


# Why This Strategy Exists

Traditional retail strategies react purely to price crosses, MA thresholds, or chart patterns, ignoring the macroeconomic context that drives fixed-income markets.

Bond performance is heavily tied to:

- Inflation direction

- Policy expectations

- Growth momentum

- Yield curve shape

- Market volatility regimes

This project addresses two major weaknesses of purely price-driven strategies:

Problem	Macro Layer Benefit
Whipsaws on false breakouts	Filters entries
Late exits after macro shifts	Validates urgency

This system blends price responsiveness with macro validation, mirroring how professional macro desks operate.

# Core Assumptions

The strategy is built on the following economically defensible assumptions:

Economic Condition	Policy Incentive	Duration Result
Inflation falling	Easing bias	TLT positive
Growth stable	Neutral policy	AGG stable
Inflation accelerating	Tightening	Duration negative
High uncertainty	Defensive	SHY preferred

Bonds don’t move only because yields changed —
They move because expectations changed.

Macro data is slow, price data is fast:

Price = timing

Macro = validation

# Data Sources
Dataset	Frequency	Role
SHY, AGG, TLT prices	Daily	Trend signals
CPI YoY	Monthly	Inflation filter
Optional — ISM PMI	Monthly	Growth momentum
Optional — 2y–10y spread	Daily	Recession risk
Optional — MOVE index	Daily	Volatility regime

Price → Fast reacting, noisy
Macro → Slow reacting, stable

Combining improves robustness.

# Strategy Logic (High Level)
Price Trigger

Uses return lookback, MA cross, or both to determine potential entry timing


 Macro Filter: 

| Inflation + Curve \\ Growth + Labor | **G↓, U↑**<br>Growth slowing, labor weakening | **G↓, U↓**<br>Growth slowing, labor strong | **G↑, U↑**<br>Growth improving, labor weak | **G↑, U↓**<br>Growth improving, labor strong |
|:----------------------------------|:--------------------------------------------|:-------------------------------------------|:-------------------------------------------|:--------------------------------------------|
| **DIS + INV**<br>Strong disinflation, inverted curve | **TLT if momentum+, else AGG**<br> | **TLT if momentum+, else AGG** | **AGG** | **AGG** |
| **DIS + NORM**<br>Disinflation, normal curve | **TLT if momentum+, else AGG** | **AGG** | **AGG** | **AGG** |
| **STB + INV**<br>Stable inflation, inverted curve | **AGG (defensive)**<br>SHY only if AGG momentum negative | **AGG** | **AGG or SHY (price-driven)** | **AGG** |
| **STB + NORM**<br>Stable inflation, normal curve | **AGG** | **AGG** | **AGG** | **AGG** |
| **INF + INV**<br>Inflation rising, inverted curve | **SHY** | **SHY** | **SHY** | **SHY** |
| **INF + NORM**<br>Inflation rising, normal curve | **SHY** | **SHY** | **SHY** | **SHY** |



The table defines which assets are permitted by macro regime, while price momentum determines when higher-conviction allocations (TLT) are executed; AGG serves as the default bond exposure and SHY is reserved for inflation-hostile environments.


# Risk Philosophy

This is not a forecasting model, it does not predict what the Fed will do.

It responds to ongoing regime transitions earlier than macro-only, later than price-only and is more stable than both individually

This strategy prioritizes avoiding large drawdowns, participating in sustained trends and reducing emotional decision-making

# Flow:

Fetch price + macro data

Compute trend + derivative macro signals

Generate allocation decision

Log + notify + visualize

# Summary

This project creates a rule-based ETF rotation model based on macroeconomic derivatives (not just raw values), combined with price-based momentum (for timing). It is designed for durability across regimes without relying on prediction or subjective bias

Future versions of this application aim to include:

- Backtesting (this is a top priority and will be implemented ASAP)

- Shorting

- Volatility scaling

- Term-structure signals

- Equity integration

- Optimization

- ML-based regime classifier (far future)

But Version 1 succeeds with simplicity + strong reasoning.
```

                         ┌────────────────┐
                         │ Scheduler (EOD)│
                         │  Cron / Task   │
                         └───────┬────────┘
                                 │
                 ┌───────────────┼───────────────┐
                 │                               │
      ┌───────────────────────┐     ┌─────────────────────────┐
      │  ETF Price Data Fetch │     │ Macro Data Fetch        │
      │  (SHY / AGG / TLT)    │     │ CPI, PMI, Curve, MOVE   │
      │  Daily via FMP API    │     │ FRED API (monthly/daily)│
      └──────────┬────────────┘     └────────────┬────────────┘
                 │                               │
                 ▼                               ▼
       ┌─────────────────────┐        ┌───────────────────────┐
       │ Price Signal Engine │        │ Macro Signal Engine   │
       │ - Returns / MAs     │        │ - Direction (1st der) │
       │ - Trend detection   │        │ - Acceleration (2nd)  │
       └──────────┬──────────┘        └───────────┬───────────┘
                  │                               │
                  └──────────────┬────────────────┘
                                 ▼
                       ┌─────────────────────┐
                       │ Decision Engine     │
                       │Combine (Price+Macro)│
                       │ TLT / AGG / SHY     │
                       └──────────┬──────────┘
                                  │
                 ┌────────────────┼─────────────────┐
                 │                                  │
         ┌────────────────┐                 ┌─────────────────────┐
         │ Trade Logger   │                 │ Notification System │
         │ CSV / DB Store │                 │ Email / SMS / UI    │
         └───────┬────────┘                 └───────────┬─────────┘
                 │                                      │
                 ▼                                      ▼
      ┌───────────────────────┐           ┌─────────────────────────┐
      │ Backtest + Analytics  │           │ Front End Visualization │
      │ Drawdown / Sharpe etc │           │ Charts / Signals / Macro│
      └──────────┬────────────┘           └─────────────┬───────────┘
                 │                                      │
                 └──────────────────────────────────────┘
                                   Feedback loop
```

# Expected Timeline:
### V 1.x.x - Measurement and Execution Realism
#### V 1.2.0
- Full Analytics Dashboard (streamlit for early stage, React once full product is complete)
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