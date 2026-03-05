from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class PortfolioSnapshot:
    date: str
    cash: float
    holdings: Dict[str, float]
    prices: Dict[str, float] #later; this may become Dict[str, Dict[str, float]]
    nav: float


def value_portfolio(
    *,
    date: str,
    cash: float,
    holdings: Dict[str, float],
    prices: Dict[str, float],
) -> PortfolioSnapshot:

    nav = float(cash)

    for asset, units in holdings.items():
        if asset not in prices:
            raise KeyError(f"Missing price for {asset}") #quick debug
        px = float(prices[asset])
        nav += float(units) * px

    return PortfolioSnapshot(
        date=str(date),
        cash=float(cash),
        holdings=dict(holdings),
        prices=dict(prices),
        nav=nav,
    )
