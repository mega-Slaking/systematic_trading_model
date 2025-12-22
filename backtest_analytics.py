from src.visuals.backtest_analysis import (
    load_results,
    plot_nav,
    plot_drawdown,
    plot_exposure
)

relaxed = load_results("output/backtests/backtest_results.csv")

plot_nav([ relaxed], [ "Relaxed"], "nav")
plot_drawdown(relaxed, "relaxed")
plot_exposure(relaxed, "relaxed")
