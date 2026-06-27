# Reference Strategy — Methodology

This document holds the full methodology for the platform's **reference
strategy**: a regime-conditional rotation across three U.S. Treasury bond ETFs.
The README keeps only a concise summary; the detail lives here.

The reference strategy is one instantiation of the platform's research pipeline.
The same engine, backtester, execution simulator, and analytics support any
strategy expressed as a `StrategyConfig` in the registry.

---

## Universe

The strategy tilts a portfolio across three U.S. Treasury–focused bond ETFs:

- **TLT** — Long-duration Treasuries
- **AGG** — Broad U.S. bond market
- **SHY** — Short-duration, "cash-like" Treasuries

It uses a hybrid decision framework that combines:

- **Price-based trend and momentum signals**, which provide a faster reaction to
  changing market conditions.
- **Macro-based direction and acceleration filters**, which act as a
  slower-moving regime validation layer.
- **Volatility- and covariance-aware position sizing**, which adjusts exposure
  based on estimated asset and portfolio risk.

The system participates in bond rallies when price and macro conditions are
supportive, reduces duration exposure during tightening or unstable macro
regimes, and rotates toward lower-risk bond exposure when conviction is weaker.
Rather than relying on explicit rate forecasts or discretionary assumptions about
future policy, the engine uses observable market and macro states to make
systematic allocation decisions.

---

## Goal of the Strategy

The core goal is to allocate across bond exposures based on the prevailing
monetary and macro regime, rotating toward assets better suited to the current
environment while reducing duration exposure when macro instability or inflation
risk outweighs the expected reward.

In simplified terms:

- When disinflation and weakening growth conditions are supportive of duration,
  the strategy can increase exposure to longer-duration bonds such as TLT.
- When macro conditions are stable and non-accelerating, the strategy can favour
  a broader intermediate bond allocation such as AGG.
- When inflation pressure, policy uncertainty, or macro instability rises, the
  strategy can reduce duration exposure and rotate toward lower-duration assets
  such as SHY.

The strategy is designed to be:

- Simple enough to understand.
- Systematic enough to reduce emotional decision-making.
- Flexible enough to evolve through new signals, sizing methods, and scenario
  testing.
- Grounded in economic reasoning rather than hindsight-fitted rules.

---

## Core Assumptions

The strategy is built on the following economically motivated assumptions:

| Economic Condition | Policy / Market Interpretation | Preferred Duration Exposure |
|---|---|---|
| Inflation falling | Easing expectations may increase | Longer duration can benefit |
| Growth weakening | Defensive demand for bonds may rise | Longer duration can benefit |
| Growth stable and inflation non-accelerating | Policy environment may remain balanced | Broad bond exposure can be appropriate |
| Inflation accelerating | Tightening expectations may increase | Duration exposure should be reduced |
| High macro uncertainty | Risk control becomes more important | Lower-duration exposure may be preferred |

Bonds do not move only because yields have changed. They move because
expectations about inflation, growth, policy, and risk have changed. Macro data
is slower-moving, while price data reacts faster:

- Price signals help with timing.
- Macro signals help with validation.
- Volatility and covariance estimates help with risk sizing.

---

## Strategy Logic

At a high level, the strategy converts market and macro conditions into a
systematic allocation decision across TLT, AGG, and SHY.

The engine does not rely on a single rule, moving-average crossover, or static
macro lookup table. Instead, it uses a modular decision pipeline that separates
signal generation, regime interpretation, conviction scoring, risk-aware sizing,
and portfolio constraints.

### Signal Inputs

The strategy currently uses two main categories of signals.

**Price signals** provide the faster-moving view of the market. They identify
whether each asset is currently behaving favourably from a trend or momentum
perspective, helping determine timing and whether the market is confirming the
macro view. Examples include:

- Recent return behaviour
- Trend / momentum direction
- Asset-level price confirmation
- Missing-price and data-quality checks

**Macro signals** provide the slower-moving economic context. They identify
whether the broader environment is supportive or hostile for duration exposure.
The macro layer focuses on:

- Inflation direction
- Growth direction
- Macro acceleration or deceleration
- Labour-market strength or weakness
- Regime stability or instability

The macro layer is not a policy forecaster; it acts as a validation layer for
deciding whether duration exposure is economically justified.

---

## Decision Framework

The strategy uses a decision framework rather than a fixed allocation table.
Each run produces a `Decision` object that carries strategy state through the
pipeline, progressively enriched with:

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
- Trace / debug metadata

This makes the system easier to test, inspect, and extend.

### Allocation Intuition

The simplified economic logic is:

| Environment | Strategy Interpretation | Allocation Bias |
|---|---|---|
| Disinflation + weakening growth | Conditions may support duration | Increase long-duration exposure, typically TLT |
| Stable growth + non-accelerating inflation | Balanced bond environment | Favour broad bond exposure, typically AGG |
| Re-accelerating inflation or tightening pressure | Duration risk is less attractive | Reduce TLT exposure |
| High uncertainty or weak conviction | Risk control becomes more important | Rotate toward lower-duration exposure, typically SHY |

These are not hard-coded forecasts. They are economic priors that guide how the
system interprets observable price and macro data. The final allocation is then
adjusted by the risk layer.

---

## Experimental Architecture

The strategy is designed to support controlled experimentation. Different
scenario configurations can be tested by changing config objects rather than
rewriting strategy logic. Examples of configurable experiments include:

- **Volatility estimation method** — rolling standard deviation, EWMA, GARCH.
- **Volatility scaling behaviour** — scaling on/off, different lookback windows,
  different scaling powers.
- **Covariance modelling** — sample covariance, EWMA covariance, portfolio
  volatility targeting.
- **Allocation profiles** — current base allocation logic, legacy
  conviction-driven allocation logic, future strategy variants.
- **Conviction profiles** — conviction disabled, conviction-driven sizing,
  future macro/price confidence models.

The goal is to make strategy development empirical. Instead of relying on a
single backtest result, the system compares multiple strategy configurations
under the same data, execution, cost, and portfolio assumptions.

---

## Experimental Findings

Running the strategy registry through the experimental backtesting framework
produced a clear and somewhat counterintuitive result: **the risk-layer
machinery — position-sizing method, asset-wise volatility scaling, and
covariance-based portfolio volatility targeting — had negligible effect on
realised capital gains.** The most profitable configurations were those that
*did not* apply covariance scaling or asset-wise volatility scaling, or that used
low volatility-scaling powers. The cumulative return is driven overwhelmingly by
the regime-conditional allocation across TLT/AGG/SHY, not by the volatility
normalisation applied on top of it.

This is consistent with Harvey et al. (2018) [^harvey2018], who studied the
impact of volatility targeting across asset classes and found that while
volatility targeting improved risk-adjusted returns (Sharpe ratio) for equities,
it had **essentially no effect on the Sharpe ratio of government bonds**. Our
findings extend the same intuition to this bond-rotation strategy: because the
underlying duration exposures are already relatively well-behaved in volatility
terms, the additional volatility- and covariance-based normalisation contributes
little incremental performance and, in the most profitable variants, is best left
off or heavily damped.

[^harvey2018]: Harvey, C. R., Hoyle, E., Korgaonkar, R., Rattray, S., Sargaison, M., & van Hemert, O. (2018). *The Impact of Volatility Targeting*. SSRN Working Paper. <http://dx.doi.org/10.2139/ssrn.3175538>
