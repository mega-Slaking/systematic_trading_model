from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


Side = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class Trade:
    date: str
    ticker: str
    side: Side

    qty: float                 # absolute shares traded
    price_mid: float           # reference price (e.g., close)
    price_exec: float          # mid +/- slippage

    notional_mid: float        # qty * price_mid
    notional_exec: float       # qty * price_exec

    slippage_bps: float
    fee_bps: float

    slippage_cost: float
    fee_cost: float           
    total_cost: float

    reason: Optional[str] = None  #optional


@dataclass(frozen=True)
class ExecutionCosts:
    fee_bps: dict[str, float]
    slippage_bps: dict[str, float]
    min_trade_notional: float = 0.0
