"""Phase 5 — price and volatility direction context.

Distinguishes *favourable* from *adverse* volatility by combining adjusted-price
direction with volatility direction. Price-direction features are computed
**as-of `t-1`** (``prices.shift(1).pct_change(h)``) so they share the exact
information boundary of the already one-day-lagged volatility surface (§4.4):
the snapshot dated ``t`` uses price information through ``t-1`` only, with no
look-ahead relative to the strategy's own decision timing.

Yield enrichment is **out of scope** (§4.5): ``gs10``/``gs2`` are monthly-ffilled
FRED data, so a "20-day yield change" would be a misleading staircase. Daily-yield
context is deferred until a validated, lagged daily ``DGS10``/``DGS2`` source with
its own point-in-time contract exists.

Interpretation matrix (price × volatility direction):

| Price   | Vol     | Interpretation                |
| ------- | ------- | ----------------------------- |
| Falling | Rising  | Adverse Shock                 |
| Rising  | Rising  | Positive Volatility Expansion |
| Rising  | Falling | Stable Positive Trend         |
| Falling | Falling | Controlled Decline            |
| Flat    | Stable  | Quiet / Range-Bound           |
| missing | any     | Unknown                       |

Any remaining partial combination (one side Flat/Stable, the other directional)
carries no clear joint signal and is reported as **Quiet / Range-Bound**.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Tiny price moves (|return| <= this) count as Flat. Configurable.
PRICE_DIRECTION_THRESHOLD = 0.01

_JOINT_LABELS: dict[tuple[str, str], str] = {
    ("Falling", "Rising"): "Adverse Shock",
    ("Rising", "Rising"): "Positive Volatility Expansion",
    ("Rising", "Falling"): "Stable Positive Trend",
    ("Falling", "Falling"): "Controlled Decline",
}


def compute_price_direction_features(
    prices: pd.Series,
    horizons: tuple[int, ...] = (5, 20, 60),
) -> pd.DataFrame:
    """As-of `t-1` price returns over the given horizons (no look-ahead).

    Each column ``price_return_{h}d`` is ``prices.shift(1).pct_change(h)`` — the
    h-day return ending at ``t-1`` — so changing the price *on* ``t`` cannot alter
    the row dated ``t``. Division by a zero prior price yields ``NaN``.
    """
    lagged = prices.shift(1)
    return pd.DataFrame(
        {
            f"price_return_{h}d": lagged.pct_change(h, fill_method=None).replace(
                [np.inf, -np.inf], np.nan
            )
            for h in horizons
        }
    )


def classify_price_volatility_context(
    asset_return: float | None,
    vol_change: float | None,
    price_threshold: float,
    vol_threshold: float,
) -> str:
    """Joint price/volatility context label from the interpretation matrix.

    ``asset_return`` is an as-of-``t-1`` price return; ``vol_change`` is the
    relative volatility change (Phase 2). Either missing -> ``Unknown``. Both
    directional -> the matrix label; otherwise -> ``Quiet / Range-Bound``.
    """
    price = _price_direction(asset_return, price_threshold)
    vol = _vol_direction(vol_change, vol_threshold)

    if price == "Unknown" or vol == "Unknown":
        return "Unknown"
    return _JOINT_LABELS.get((price, vol), "Quiet / Range-Bound")


def _price_direction(value: float | None, threshold: float) -> str:
    if _missing(value):
        return "Unknown"
    v = float(value)
    if v > threshold:
        return "Rising"
    if v < -threshold:
        return "Falling"
    return "Flat"


def _vol_direction(value: float | None, threshold: float) -> str:
    if _missing(value):
        return "Unknown"
    v = float(value)
    if v > threshold:
        return "Rising"
    if v < -threshold:
        return "Falling"
    return "Stable"


def _missing(value: float | None) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))
