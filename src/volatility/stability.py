"""Phase 8 — volatility of volatility and estimate stability.

Measures whether the volatility **estimate itself** is steady or jumping around.
The raw ``vol_of_vol`` mixes daily-frequency variation of an already-annualised
quantity (``annualised-vol pp per day``), so its absolute number is dimensionally
muddy and **not** a headline figure — the **percentile** of vol-of-vol against the
asset's own history is the only cleanly interpretable output, and the status band
is derived from that percentile.

All point-in-time on the already-lagged surface (§4.1): ``vol_of_vol`` at row ``t``
uses vol values through ``t`` only, and its percentile reuses the Phase 1 algorithm,
so nothing here introduces look-ahead.
"""

from __future__ import annotations

import math

import pandas as pd

# Stability status bands on the vol-of-vol **percentile** (0.0–1.0). Configurable.
#   < 0.60 Stable | 0.60–0.80 Changing | 0.80–0.95 Unstable | > 0.95 Extreme instability
STABILITY_THRESHOLDS: dict[str, float] = {"changing": 0.60, "unstable": 0.80, "extreme": 0.95}


def compute_volatility_of_volatility(vol_series: pd.Series, window: int = 20) -> pd.Series:
    """Rolling std of daily changes in the (annualised) volatility estimate.

    ``vol_series.diff().rolling(window).std()`` — point-in-time, so row ``t`` reads
    only vol values up to ``t``. The result is the "20D standard deviation of daily
    changes in annualised volatility"; interpret it via its percentile, not its
    raw magnitude.
    """
    return vol_series.diff().rolling(window).std()


def classify_estimate_stability(
    stability_percentile: float | None,
    thresholds: dict[str, float] = STABILITY_THRESHOLDS,
) -> str:
    """Map a 0.0–1.0 vol-of-vol percentile to Stable / Changing / Unstable / Extreme instability.

    Bands: ``> extreme`` (0.95) is Extreme instability; ``>= unstable`` (0.80) is
    Unstable; ``>= changing`` (0.60) is Changing; otherwise Stable. ``None``/``NaN``
    returns ``Unknown``.
    """
    if stability_percentile is None:
        return "Unknown"
    p = float(stability_percentile)
    if math.isnan(p):
        return "Unknown"

    if p > thresholds["extreme"]:
        return "Extreme instability"
    if p >= thresholds["unstable"]:
        return "Unstable"
    if p >= thresholds["changing"]:
        return "Changing"
    return "Stable"


def stability_reference_lines(thresholds: dict[str, float] = STABILITY_THRESHOLDS) -> list[float]:
    """The stability band edges for chart guides, ascending ([0.60, 0.80, 0.95])."""
    return sorted(thresholds.values())
