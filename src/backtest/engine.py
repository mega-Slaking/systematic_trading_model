import logging

import pandas as pd

from src.decision.models import Decision
from src.engine.run import run_engine
from src.context.backtest import BacktestContext
from src.utils.ensure_long import ensure_long
from src.accounting.valuation import value_portfolio
from src.accounting.metrics import compute_day_metrics

logger = logging.getLogger(__name__)


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


def _log_decision_debug(decision: Decision, prefix: str = "") -> None:
    logger.debug("%sDECISION DEBUG", prefix)
    logger.debug("date: %s", decision.date)
    logger.debug("regime: %s", decision.regime)
    logger.debug("monetary_regime: %s", decision.monetary_regime)
    logger.debug("economic_regime: %s", decision.economic_regime)
    logger.debug("reason: %s", decision.reason)

    logger.debug("direction: %s", decision.direction)
    logger.debug("base_weights: %s", decision.base_weights)
    logger.debug("conviction: %s", decision.conviction)
    logger.debug("conviction_scores: %s", decision.conviction_scores)
    logger.debug("conviction_components: %s", decision.conviction_components)
    logger.debug("conviction_weights: %s", decision.conviction_weights)
    logger.debug("sized_weights: %s", decision.sized_weights)
    logger.debug("final_weights: %s", decision.final_weights)

    logger.debug("gross_exposure: %s", decision.gross_exposure)
    logger.debug("net_exposure: %s", decision.net_exposure)
    logger.debug("portfolio_vol_estimate: %s", decision.portfolio_vol_estimate)
    logger.debug("portfolio_vol_target: %s", decision.portfolio_vol_target)
    logger.debug("portfolio_scale: %s", decision.portfolio_scale)

    if decision.notes:
        logger.debug("notes:")
        for note in decision.notes[-8:]:
            logger.debug("  - %s", note)


def run_backtest(etf_history, macro_history, portfolio,scenario, returns_view=None, volatility_feature_surface=None):
    etf_history = ensure_long(etf_history)
    context = BacktestContext(etf_history, macro_history, portfolio)

    context.returns_view = returns_view
    context.volatility_feature_surface = volatility_feature_surface

    dates = sorted(etf_history["date"].dropna().unique())
    logger.debug(
        "DATES: %s FIRST: %s LAST: %s",
        len(dates), dates[0] if dates else None, dates[-1] if dates else None,
    )

    skip_decision = 0
    skip_prices = 0
    executed = 0
    nav_prev = None
    last_decision = None

    for date in dates:
        context.set_date(pd.Timestamp(date))
        as_of = str(context.current_date)

        decision = run_engine(context, scenario=scenario)
        if decision is None:
            skip_decision += 1
            if skip_decision <= 5:
                logger.debug("SKIP decision None on %s", context.current_date)
            continue

        last_decision = decision
        prices_today = context.get_prices_today()
        if prices_today is None:
            skip_prices += 1
            if skip_prices <= 5:
                logger.debug("SKIP prices None on %s", context.current_date)
                etf_df = context.fetch_etf_prices()
                logger.debug("  tickers in slice: %s", sorted(etf_df["ticker"].dropna().unique().tolist()))
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

    # ----- run summary (debug) -----
    logger.debug(
        "SUMMARY executed=%s skip_decision=%s skip_prices=%s",
        executed, skip_decision, skip_prices,
    )
    trade_days = sum(1 for r in context.daily_metrics if r["gross_trade_notional"] > 0)
    total_cost = sum(r["total_cost"] for r in context.daily_metrics)
    avg_cost_per_trade_day = total_cost / trade_days if trade_days > 0 else 0.0
    logger.debug("Trade days: %s", trade_days)
    logger.debug("Total costs paid: %s", total_cost)
    logger.debug("Average cost per trade day: %s", avg_cost_per_trade_day)
    logger.debug("results rows: %s", len(context.results))
    logger.debug("daily_metrics rows: %s", len(context.daily_metrics))
    logger.debug("trade_log rows: %s", len(context.trade_log))
    if last_decision is not None:
        _log_decision_debug(last_decision, prefix="LAST DAY ")

    if context.results:
        logger.debug("results NAV first/last: %s %s", context.results[0]["nav"], context.results[-1]["nav"])

    if context.daily_metrics:
        logger.debug("daily_metrics NAV first/last: %s %s", context.daily_metrics[0]["nav"], context.daily_metrics[-1]["nav"])

    return context
