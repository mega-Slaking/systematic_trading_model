import pandas as pd
from src.visuals.backtest_analysis import (
    load_results,
    plot_nav,
    plot_drawdown,
    plot_exposure,
    build_buy_and_hold_nav,
    plot_inflation_regime,
    plot_growth_regime,
    plot_labour_regime,
    plot_curve_state,
    plot_macro_supports_duration
)

strategy = load_results("output/backtests/backtest_results.csv")
etf_prices = load_results("data/raw/etf_prices.csv")

tlt_nav = build_buy_and_hold_nav(etf_prices, "TLT")
agg_nav = build_buy_and_hold_nav(etf_prices, "AGG")
shy_nav = build_buy_and_hold_nav(etf_prices, "SHY")

plot_nav([strategy], [ "Relaxed"], "nav")
plot_nav(
    dfs=[strategy, tlt_nav, agg_nav, shy_nav],
    labels=["Strategy","TLT Buy & Hold", "AGG Buy & Hold", "SHY Buy & Hold"],
    name="nav_comparison"
)
plot_drawdown(strategy, "relaxed")
plot_drawdown(tlt_nav, "tlt")
plot_drawdown(agg_nav, "agg")
plot_drawdown(shy_nav, "shy")
plot_exposure(strategy, "relaxed")
regimes = pd.read_csv("output/backtests/regime_trace.csv", parse_dates=["date"])
regimes = regimes.sort_values("date")
plot_inflation_regime(regimes, "backtest")
plot_growth_regime(regimes, "backtest")
plot_labour_regime(regimes, "backtest")
plot_curve_state(regimes, "backtest")
plot_macro_supports_duration(regimes, "backtest")
#consider compact regime dashboard
