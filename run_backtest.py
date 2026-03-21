from src.backtest.engine import run_backtest
from src.backtest.portfolio import Portfolio
from src.storage.backtest_persister import save_backtest_results
from src.api_fetch.fetch_etf_prices import fetch_etf_prices
from src.api_fetch.fetch_macro_data import fetch_macro_data
from src.storage.db_writer import insert_backtest_results, insert_backtest_decision_trace, insert_backtest_regime_trace
from src.storage.db_reader import get_etf_history, get_macro_history
import pandas as pd
import sqlite3

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

    start_date = max(etf_start, macro_start)

    etf_history = etf_history[etf_history["date"] >= start_date]

    portfolio = Portfolio(initial_capital=1_000_000)

    context = run_backtest(etf_history, macro_history, portfolio)

    save_backtest_results(context.daily_metrics)
    insert_backtest_results(conn, context.daily_metrics)
    pd.DataFrame(context.decision_trace).to_csv(
        "output/backtests/decision_trace.csv",
        index=False
    )
    insert_backtest_decision_trace(conn, context.decision_trace)
    pd.DataFrame(context.regime_trace).to_csv(
        "output/backtests/regime_trace.csv",
        index=False
    )
    insert_backtest_regime_trace(conn, context.regime_trace)
    print("Backtest complete.")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
