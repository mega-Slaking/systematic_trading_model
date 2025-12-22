from src.backtest.engine import run_backtest
from src.backtest.portfolio import Portfolio
from src.storage.backtest_persister import save_backtest_results
from src.api_fetch.fetch_etf_prices import fetch_etf_prices
from src.api_fetch.fetch_macro_data import fetch_macro_data
import pandas as pd

def main():
    print("Running backtest. Please be patient...")
    #etf_history = fetch_etf_prices()
    #macro_history = fetch_macro_data()
    #debug for now to see where non determinism comes from
    etf_history = pd.read_csv(
        "data/raw/etf_prices.csv",
        parse_dates=["date"]
    )

    macro_history = pd.read_csv(
        "data/raw/macro_cpi.csv",
        parse_dates=["date"]
    )

    etf_history = etf_history.dropna(subset=["date"])
    macro_history = macro_history.dropna(subset=["date"])

    required = {"AGG", "SHY", "TLT"}

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

    results = run_backtest(etf_history, macro_history, portfolio)

    save_backtest_results(results)
    print("Backtest complete.")


if __name__ == "__main__":
    main()
