import pandas as pd

from src.engine.run import run_engine
from src.context.backtest import BacktestContext
from src.utils.ensure_long import ensure_long


def run_backtest(etf_history, macro_history, portfolio):
    etf_history = ensure_long(etf_history)

    context = BacktestContext(etf_history, macro_history, portfolio)

    dates = sorted(etf_history["date"].dropna().unique())
    print("DATES:", len(dates), "FIRST:", dates[0] if dates else None, "LAST:", dates[-1] if dates else None)

    skip_decision = 0
    skip_prices = 0
    executed = 0

    for date in dates:
        context.set_date(pd.Timestamp(date))

        # prove the loop is running
        # (print occasionally so you don't spam)
        if executed == 0 and (skip_decision + skip_prices) < 3:
            print("LOOP DATE:", context.current_date)

        decision = run_engine(context)
        if decision is None:
            skip_decision += 1
            if skip_decision <= 5:
                print("SKIP decision None on", context.current_date)
            continue

        prices_today = context.get_prices_today()
        if prices_today is None:
            skip_prices += 1
            if skip_prices <= 5:
                print("SKIP prices None on", context.current_date)
                # show what tickers exist in the slice (this is the key insight)
                etf_df = context.fetch_etf_prices()
                print("  tickers in slice:", sorted(etf_df["ticker"].dropna().unique().tolist()))
            continue

        executed += 1
        if executed <= 5:
            print("EXECUTE", context.current_date, "chosen:", decision.get("chosen"), "prices:", prices_today)

        context.portfolio.mark_to_market(prices_today)
        context.portfolio.rebalance(decision, prices_today)
        #context.results["decision_trace"] = context.decision_trace

    print("SUMMARY executed=", executed, "skip_decision=", skip_decision, "skip_prices=", skip_prices)
    return context