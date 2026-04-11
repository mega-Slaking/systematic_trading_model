import pandas as pd

from src.engine.run import run_engine
from src.context.backtest import BacktestContext
from src.utils.ensure_long import ensure_long
from src.accounting.valuation import value_portfolio
from src.accounting.metrics import compute_day_metrics

def _weights_from_holdings(holdings: dict[str, float], prices: dict[str, float], nav: float) -> dict[str, float]:
    nav = float(nav)
    if nav == 0.0:
        return {}

    w: dict[str, float] = {}
    for a, u in holdings.items():
        if u == 0:
            continue
        px = float(prices[a])
        w[a] = (float(u) * px) / nav

    return w

def run_backtest(etf_history, macro_history, portfolio,scenario):
    etf_history = ensure_long(etf_history)
    context = BacktestContext(etf_history, macro_history, portfolio)

    dates = sorted(etf_history["date"].dropna().unique())
    print("DATES:", len(dates), "FIRST:", dates[0] if dates else None, "LAST:", dates[-1] if dates else None)

    skip_decision = 0
    skip_prices = 0
    executed = 0
    nav_prev = None

    for date in dates:
        context.set_date(pd.Timestamp(date))
        as_of = str(context.current_date)

        decision = run_engine(context, scenario=scenario)
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
                etf_df = context.fetch_etf_prices()
                print("  tickers in slice:", sorted(etf_df["ticker"].dropna().unique().tolist()))
            continue

        executed += 1
        #Value before trading
        snap_pre = value_portfolio(
            date=as_of,
            cash=context.portfolio.cash,
            holdings=context.portfolio.holdings,
            prices=prices_today,
        )

        #Trade
        trades = context.portfolio.rebalance_v2(decision, prices_today, context.current_date)

        #Value after trading
        snap_post = value_portfolio(
            date=as_of,
            cash=context.portfolio.cash,
            holdings=context.portfolio.holdings,
            prices=prices_today,
        )

        #Metrics
        day = compute_day_metrics(
            date=as_of,
            nav=snap_post.nav,
            nav_prev=nav_prev,
            trades=trades,
        )

        weights_post = _weights_from_holdings(
            context.portfolio.holdings,
            prices_today,
            snap_post.nav
        )

        context.daily_metrics.append({
        "date": day.date,
        "nav_pre": snap_pre.nav,
        "nav": day.nav,
        "ret": day.ret,
        "turnover": day.turnover,
        "fee_cost": day.fee_cost,
        "slippage_cost": day.slippage_cost,
        "total_cost": day.total_cost,
        "gross_trade_notional": day.gross_trade_notional,
        "weights": dict(weights_post),
        "n_positions": len(weights_post),
        "top_asset": max(weights_post, key=weights_post.get) if weights_post else None,
        "top_weight": max(weights_post.values()) if weights_post else 0.0,
    })

        for t in trades:
            context.trade_log.append({
                "date": t.date,
                "ticker": t.ticker,
                "side": t.side,
                "qty": t.qty,
                "price_mid": t.price_mid,
                "price_exec": t.price_exec,
                "notional_mid": t.notional_mid,
                "notional_exec": t.notional_exec,
                "fee_cost": t.fee_cost,
                "slippage_cost": t.slippage_cost,
                "total_cost": t.total_cost,
                "reason": t.reason,
            })
        nav_prev = day.nav

    ###################### DEBUG ####################################
    print("SUMMARY executed=", executed, "skip_decision=", skip_decision, "skip_prices=", skip_prices)
    print("Total costs paid:", sum(r["total_cost"] for r in context.daily_metrics))
    trade_days = sum(1 for r in context.daily_metrics if r["gross_trade_notional"] > 0)
    print("Trade days:", trade_days)
    total_cost = sum(r["total_cost"] for r in context.daily_metrics)
    avg_cost_per_trade_day = total_cost / trade_days if trade_days > 0 else 0.0
    print("Total costs paid:", total_cost)
    print("Average cost per trade day:", avg_cost_per_trade_day)
    print("results rows:", len(context.results))
    print("daily_metrics rows:", len(context.daily_metrics))
    print("trade_log rows:", len(context.trade_log))

    if context.results:
        print("results NAV first/last:", context.results[0]["nav"], context.results[-1]["nav"])

    if context.daily_metrics:
        print("daily_metrics NAV first/last:", context.daily_metrics[0]["nav"], context.daily_metrics[-1]["nav"])

    return context