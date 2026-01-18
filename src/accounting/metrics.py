from dataclasses import dataclass
from typing import List

from src.execution.models import Trade


@dataclass(frozen=True)
class DayMetrics:
    date: str
    nav: float
    ret: float                  # daily return
    gross_trade_notional: float # sum(|notional_mid|)
    fee_cost: float
    slippage_cost: float
    total_cost: float
    turnover: float


def compute_day_metrics(
    *,
    date: str,
    nav: float,
    nav_prev: float | None,
    trades: List[Trade],
) -> DayMetrics:
    nav = float(nav)
    if nav_prev is None or nav_prev <= 0:
        ret = 0.0
        denom = nav if nav > 0 else 1.0
    else:
        ret = (nav / float(nav_prev)) - 1.0
        denom = float(nav_prev)

    gross_trade_notional = sum(abs(float(t.notional_mid)) for t in trades)
    fee_cost = sum(float(t.fee_cost) for t in trades)
    slippage_cost = sum(float(t.slippage_cost) for t in trades)
    total_cost = fee_cost + slippage_cost

    turnover = (gross_trade_notional / denom) if denom > 0 else 0.0

    return DayMetrics(
        date=str(date),
        nav=nav,
        ret=ret,
        gross_trade_notional=gross_trade_notional,
        fee_cost=fee_cost,
        slippage_cost=slippage_cost,
        total_cost=total_cost,
        turnover=turnover,
    )