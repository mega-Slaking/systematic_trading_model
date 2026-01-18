from __future__ import annotations

from typing import Dict, List
from .models import Trade, ExecutionCosts

def _bps_to_rate(bps: float) -> float:
    return float(bps) / 10_000.0

def generate_single_asset_rebalance_trades(
    *,
    date: str,
    current_asset: str | None,
    current_units: float,
    cash_available: float,
    target_asset: str,
    prices: Dict[str, float],
    costs: ExecutionCosts,
    reason: str = "rebalance",
) -> List[Trade]:
    trades: List[Trade] = []
    cash = float(cash_available)

    #SELL old
    if current_asset is not None and current_asset != target_asset and current_units > 0:
        px_mid = float(prices[current_asset])

        slip_bps = float(costs.slippage_bps.get(current_asset, 0.0))
        fee_bps = float(costs.fee_bps.get(current_asset, 0.0))
        slip_rate = _bps_to_rate(slip_bps)
        fee_rate = _bps_to_rate(fee_bps)

        qty = float(current_units)
        px_exec = px_mid * (1.0 - slip_rate)  # adverse for SELL
        notional_mid = qty * px_mid
        notional_exec = qty * px_exec

        slippage_cost = qty * abs(px_exec - px_mid)
        fee_cost = notional_exec * fee_rate
        total_cost = slippage_cost + fee_cost

        trades.append(Trade(
            date=str(date), ticker=current_asset, side="SELL",
            qty=qty, price_mid=px_mid, price_exec=px_exec,
            notional_mid=notional_mid, notional_exec=notional_exec,
            slippage_bps=slip_bps, fee_bps=fee_bps,
            slippage_cost=slippage_cost, fee_cost=fee_cost, total_cost=total_cost,
            reason=reason,
        ))

        cash += (notional_exec - fee_cost)

    # BUY target
    if current_asset != target_asset:
        px_mid = float(prices[target_asset])

        slip_bps = float(costs.slippage_bps.get(target_asset, 0.0))
        fee_bps = float(costs.fee_bps.get(target_asset, 0.0))
        slip_rate = _bps_to_rate(slip_bps)
        fee_rate = _bps_to_rate(fee_bps)

        px_exec = px_mid * (1.0 + slip_rate)  # adverse for BUY

        # Cash has to cover: notional_exec + fee_cost
        # fee_cost = notional_exec * fee_rate
        # total outlay = notional_exec * (1 + fee_rate)
        # notional_exec = cash / (1 + fee_rate)
        notional_exec = cash / (1.0 + fee_rate) if cash > 0 else 0.0
        qty = notional_exec / px_exec if px_exec > 0 else 0.0

        notional_mid = qty * px_mid
        slippage_cost = qty * abs(px_exec - px_mid)
        fee_cost = notional_exec * fee_rate
        total_cost = slippage_cost + fee_cost

        trades.append(Trade(
            date=str(date), ticker=target_asset, side="BUY",
            qty=qty, price_mid=px_mid, price_exec=px_exec,
            notional_mid=notional_mid, notional_exec=notional_exec,
            slippage_bps=slip_bps, fee_bps=fee_bps,
            slippage_cost=slippage_cost, fee_cost=fee_cost, total_cost=total_cost,
            reason=reason,
        ))

    return trades