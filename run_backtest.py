from src.backtest.engine import run_backtest
from src.backtest.portfolio import Portfolio
from src.storage.db_writer import insert_backtest_results, insert_backtest_decision_trace, insert_backtest_regime_trace
from src.storage.db_reader import get_etf_history, get_macro_history
from src.scenarios.factory import build_vol_power_scenarios, build_covariance_scaling_scenarios, build_ewma_covariance_scaling_scenarios
import sqlite3
import pandas as pd

conn = sqlite3.connect("data/database.db")

def main():
    print("Running backtest. Please be patient...")
    etf_history = get_etf_history()

    macro_history = get_macro_history()

    etf_history = etf_history.dropna(subset=["date"])
    macro_history = macro_history.dropna(subset=["date"])

    required = {"AGG", "SHY", "TLT"}
    available = set(etf_history["ticker"].dropna().unique())
    missing = required - available
    if missing:
        print("WARNING: Missing required tickers in ETF history:", sorted(missing))
        print("Available tickers:", sorted(available))
        # Fallback to whatever is available for historic coverage, but strategy may be degraded.
        required = required & available

    valid_dates = (
        etf_history
        .groupby("date")["ticker"]
        .apply(lambda s: required.issubset(set(s)))
    )

    etf_start = valid_dates[valid_dates].index.min()

    macro_start = macro_history["date"].min()

    #start_date = max(etf_start, macro_start)
    start_date = max(etf_start, macro_start, pd.Timestamp("2016-01-01"))

    etf_history = etf_history[etf_history["date"] >= start_date]

    #portfolio = Portfolio(initial_capital=1_000_000)
    #context = run_backtest(etf_history, macro_history, portfolio)

    scenarios = (
        build_vol_power_scenarios()
        + build_covariance_scaling_scenarios()
        + build_ewma_covariance_scaling_scenarios()
    )
    
    for scenario in scenarios:
        print(f"Running scenario: {scenario.scenario_id}")

        portfolio = Portfolio(initial_capital=1_000_000)

        context = run_backtest(
            etf_history,
            macro_history,
            portfolio,
            scenario=scenario,
        )
        for r in context.daily_metrics:
            r["scenario_id"] = scenario.scenario_id

        for r in context.decision_trace:
            r["scenario_id"] = scenario.scenario_id

        for r in context.regime_trace:
            r["scenario_id"] = scenario.scenario_id

        insert_backtest_results(conn, context.daily_metrics)
        insert_backtest_decision_trace(conn, context.decision_trace)
        insert_backtest_regime_trace(conn, context.regime_trace)

    print("Backtest complete.")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
