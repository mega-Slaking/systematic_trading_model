from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class PortfolioSnapshot:
    date: str
    cash: float
    current_asset: str | None
    units: float
    price: float | None
    nav: float


def value_portfolio(
    *,
    date: str,
    cash: float,
    current_asset: str | None,
    units: float,
    prices: Dict[str, float],
) -> PortfolioSnapshot:
    if current_asset is None:
        return PortfolioSnapshot(
            date=str(date),
            cash=float(cash),
            current_asset=None,
            units=float(units),
            price=None,
            nav=float(cash),
        )

    px = float(prices[current_asset])
    nav = float(cash) + float(units) * px

    return PortfolioSnapshot(
        date=str(date),
        cash=float(cash),
        current_asset=current_asset,
        units=float(units),
        price=px,
        nav=nav,
    )
