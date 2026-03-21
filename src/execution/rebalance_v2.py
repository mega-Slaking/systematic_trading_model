from typing import Dict, List, Tuple
from .models import Trade, ExecutionCosts

def _bps_to_rate(bps: float) -> float:
    return float(bps) / 10_000.0

def _px_exec(px_mid: float, side: str, slip_bps: float) -> float:
    slip_rate = _bps_to_rate(slip_bps)
    if side == "BUY":
        return px_mid * (1.0 + slip_rate)  # adverse
    return px_mid * (1.0 - slip_rate)      # adverse for SELL

def _fee_cost(notional_exec: float, fee_bps: float) -> float:
    fee_rate = _bps_to_rate(fee_bps)
    return notional_exec * fee_rate

def _mk_trade(
    *,
    date: str,
    ticker: str,
    side: str,
    qty: float,
    px_mid: float,
    px_exec: float,
    slip_bps: float,
    fee_bps: float,
    reason: str,
) -> Trade:
    qty = float(qty)
    px_mid = float(px_mid)
    px_exec = float(px_exec)
    slip_bps = float(slip_bps)
    fee_bps = float(fee_bps)

    notional_mid = qty * px_mid
    notional_exec = qty * px_exec
    slippage_cost = qty * abs(px_exec - px_mid)
    fee_cost = _fee_cost(notional_exec, fee_bps)
    total_cost = slippage_cost + fee_cost

    return Trade(
        date=str(date), ticker=ticker, side=side,
        qty=qty, price_mid=px_mid, price_exec=px_exec,
        notional_mid=notional_mid, notional_exec=notional_exec,
        slippage_bps=slip_bps, fee_bps=fee_bps,
        slippage_cost=slippage_cost, fee_cost=fee_cost, total_cost=total_cost,
        reason=reason,
    )

def generate_weight_rebalance_trades(
    *,
    date: str,
    positions: Dict[str, float],           # ticker -> shares
    cash_available: float,
    target_weights: Dict[str, float],      # ticker -> weight (should sum ~1)
    prices: Dict[str, float],              # ticker -> mid price
    costs: ExecutionCosts,
    reason: str = "rebalance to weights",
    drift_tol: float = 0.0,                # e.g. 0.01
    allow_fractional: bool = True,
) -> List[Trade]:
    """
    Weight-based rebalance.
    - Computes current NAV from positions + cash.
    - Computes target $ per asset, converts to target shares.
    - Produces SELL trades first (to raise cash), then BUY trades.
    - Enforces min_trade_notional using mid notional.
    - Uses same slippage/fee model as V1.
    """

    # Universe = whatever is in target_weights (plus anything currently held)
    universe = set(target_weights.keys()) | set(positions.keys())
    universe = {t for t in universe if t in prices}  # only tradable/priced

    cash = float(cash_available)

    # Current market value
    mv = 0.0
    for tkr in universe:
        mv += float(positions.get(tkr, 0.0)) * float(prices[tkr])

    nav = cash + mv
    if nav <= 0.0:
        return []

    # Current weights (for drift check)
    current_weights: Dict[str, float] = {}
    for tkr in universe:
        val = float(positions.get(tkr, 0.0)) * float(prices[tkr])
        current_weights[tkr] = val / nav

    # Drift check: if close enough, do nothing
    if drift_tol > 0.0:
        drift = 0.0
        for tkr in universe:
            drift += abs(float(target_weights.get(tkr, 0.0)) - float(current_weights.get(tkr, 0.0)))
        drift *= 0.5  # turnover style measure; optional
        if drift < drift_tol:
            return []

    # Compute target shares from target weights (using mid prices)
    target_shares: Dict[str, float] = {}
    for tkr in universe:
        w = float(target_weights.get(tkr, 0.0))
        px_mid = float(prices[tkr])
        target_dollars = nav * w
        sh = target_dollars / px_mid if px_mid > 0 else 0.0
        if not allow_fractional:
            # You can choose floor/round; round is more symmetric but may overshoot cash.
            sh = float(int(sh))  # floor
        target_shares[tkr] = sh

    # Delta shares => trades
    deltas: List[Tuple[str, float]] = []
    for tkr in universe:
        cur = float(positions.get(tkr, 0.0))
        tgt = float(target_shares.get(tkr, 0.0))
        delta = tgt - cur
        if abs(delta) > 1e-12:
            deltas.append((tkr, delta))

    if not deltas:
        return []

    # Build SELLs first, then BUYs
    sells = [(tkr, delta) for (tkr, delta) in deltas if delta < 0]
    buys  = [(tkr, delta) for (tkr, delta) in deltas if delta > 0]

    trades: List[Trade] = []

    # ---- SELL leg ----
    for tkr, delta in sells:
        qty = abs(float(delta))
        px_mid = float(prices[tkr])
        notional_mid = qty * px_mid
        if notional_mid < float(costs.min_trade_notional):
            continue

        slip_bps = float(costs.slippage_bps.get(tkr, 0.0))
        fee_bps  = float(costs.fee_bps.get(tkr, 0.0))

        px_exec = _px_exec(px_mid, "SELL", slip_bps)
        trade = _mk_trade(
            date=date, ticker=tkr, side="SELL",
            qty=qty, px_mid=px_mid, px_exec=px_exec,
            slip_bps=slip_bps, fee_bps=fee_bps,
            reason=reason,
        )
        trades.append(trade)

        # cash increases by proceeds minus fee
        cash += (trade.notional_exec - trade.fee_cost)

    # ---- BUY leg ----
    for tkr, delta in buys:
        qty_desired = float(delta)
        px_mid = float(prices[tkr])

        slip_bps = float(costs.slippage_bps.get(tkr, 0.0))
        fee_bps  = float(costs.fee_bps.get(tkr, 0.0))
        fee_rate = _bps_to_rate(fee_bps)

        px_exec = _px_exec(px_mid, "BUY", slip_bps)

        # If we are cash-limited, cap the buy
        # total outlay = notional_exec + fee_cost = notional_exec * (1 + fee_rate)
        # notional_exec = qty * px_exec
        # cap qty by cash / (px_exec * (1 + fee_rate))
        max_qty = cash / (px_exec * (1.0 + fee_rate)) if px_exec > 0 else 0.0

        qty = min(qty_desired, max_qty)
        if not allow_fractional:
            qty = float(int(qty))  # floor

        if qty <= 1e-12:
            continue

        notional_mid = qty * px_mid
        if notional_mid < float(costs.min_trade_notional):
            continue

        trade = _mk_trade(
            date=date, ticker=tkr, side="BUY",
            qty=qty, px_mid=px_mid, px_exec=px_exec,
            slip_bps=slip_bps, fee_bps=fee_bps,
            reason=reason,
        )
        trades.append(trade)

        cash -= (trade.notional_exec + trade.fee_cost)
        if cash <= 0:
            cash = 0.0

    return trades