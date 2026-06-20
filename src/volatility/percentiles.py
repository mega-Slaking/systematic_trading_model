"""Phase 1 — point-in-time historical volatility percentiles + level classification.

Makes a raw annualised volatility interpretable relative to the asset's **own**
trailing history: "8.97% == 24th percentile == Normal". Pure, UI-agnostic, no
look-ahead — every value is computed only from observations available up to and
including the (already one-day-lagged, §4.1) row it sits on.

The percentile is the **average-rank percentile of the current observation within
its trailing window, inclusive**, computed with the vectorised
``rolling(window).rank`` / ``expanding().rank`` path (no per-row Python callback),
mirroring the rolling-baseline idiom in ``src/signals_macro/macro_signal_engine.py``.

Method choice (locked): ``method="average"`` — the symmetric/midpoint convention
(scipy ``percentileofscore(kind="mean")``). It matters only when the current value
is *tied* with others in the window; a value tied across a length-``k`` window
scores ``(k+1)/(2k)`` (→ ~0.5 for long windows), so a flat series reads as
mid-distribution rather than spuriously ``Extreme``. (``method="max"`` would return
1.0 for a constant window — rejected for exactly that reason.)
"""

from __future__ import annotations

import math

import pandas as pd

# Percentile band thresholds (0.0–1.0), upper-edge inclusive. Configurable.
#   [0.00, 0.20) Low | [0.20, 0.60) Normal | [0.60, 0.80) Elevated
#   [0.80, 0.95) High | [0.95, 1.00] Extreme
VOL_LEVEL_THRESHOLDS: dict[str, float] = {
    "low": 0.20,
    "normal": 0.60,
    "elevated": 0.80,
    "high": 0.95,
}

# Displayed when there is too little history to rank against.
LEVEL_INSUFFICIENT = "Insufficient history"


def compute_rolling_percentile(
    series: pd.Series,
    window: int | None,
    min_periods: int,
) -> pd.Series:
    """Point-in-time historical percentile (0.0–1.0) of each observation.

    Each row is the average-rank percentile of that (already-lagged) value within
    its trailing window — inclusive of itself, which is as-of ``t`` and causal,
    not future. ``window=None`` uses an expanding window ("Full" history).

    Semantics (locked, see module docstring): ``method="average"`` ties; ``NaN``
    values are excluded from the rank and a ``NaN`` current value yields ``NaN``;
    the first non-``NaN`` percentile appears only after ``min_periods`` non-``NaN``
    observations exist in the window.
    """
    if window is None:
        roller = series.expanding(min_periods=min_periods)
    else:
        # Fixed-length windows require min_periods <= window; clamp defensively so
        # a misconfigured (window < min_periods) call degrades instead of raising.
        roller = series.rolling(window=window, min_periods=min(min_periods, window))

    return roller.rank(method="average", pct=True, ascending=True)


def classify_volatility_level(
    percentile: float | None,
    thresholds: dict[str, float] = VOL_LEVEL_THRESHOLDS,
) -> str:
    """Map a 0.0–1.0 percentile to Low/Normal/Elevated/High/Extreme.

    Upper-edge rule (deterministic): a percentile exactly on a threshold falls
    into the **upper** band (``>= 0.20`` is Normal, ``>= 0.95`` is Extreme).
    ``None``/``NaN`` (insufficient history) returns :data:`LEVEL_INSUFFICIENT`.
    """
    if percentile is None:
        return LEVEL_INSUFFICIENT

    p = float(percentile)
    if math.isnan(p):
        return LEVEL_INSUFFICIENT

    if p >= thresholds["high"]:
        return "Extreme"
    if p >= thresholds["elevated"]:
        return "High"
    if p >= thresholds["normal"]:
        return "Elevated"
    if p >= thresholds["low"]:
        return "Normal"
    return "Low"


def percentile_to_ordinal(percentile: float | None) -> int | None:
    """Convert a 0.0–1.0 percentile to a 0–100 display ordinal ("24th"); None on NaN."""
    if percentile is None:
        return None

    p = float(percentile)
    if math.isnan(p):
        return None

    return int(round(p * 100))


def level_reference_lines(thresholds: dict[str, float] = VOL_LEVEL_THRESHOLDS) -> list[float]:
    """The percentile band edges for chart reference lines, ascending ([0.20, 0.60, 0.80, 0.95])."""
    return sorted(thresholds.values())
