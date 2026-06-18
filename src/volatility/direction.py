"""Phase 2 — volatility direction and the 20D/60D term ratio.

Separates **level** (Phase 1 percentile) from **direction** (is vol rising or
falling?) and adds the short/long term ratio. All point-in-time, computed on the
already one-day-lagged surface columns (§4.1) — never re-shifted.

Methodology caveat (surfaced in the UI): ``rolling_20`` and ``rolling_60`` are
built from **overlapping** return windows, so the 20D/60D ratio is mechanically
mean-reverting toward 1 and the two series are strongly correlated by
construction. The 0.85/1.15 bands are **descriptive, not statistically derived** —
read the ratio as "is short-term vol pulling away from its own baseline", not as
a ratio of independent quantities.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

# Relative-change direction thresholds (fraction): >= rising -> Rising,
# <= falling -> Falling, else Stable. Configurable.
VOL_DIRECTION_THRESHOLDS: dict[str, float] = {"rising": 0.10, "falling": -0.10}

# 20D/60D term-ratio bands: >= expansion -> Expansion, <= contraction ->
# Contraction, else Balanced. Configurable.
VOL_RATIO_BANDS: dict[str, float] = {"expansion": 1.15, "contraction": 0.85}


def compute_volatility_direction_features(
    vol_series: pd.Series,
    short_change_days: int = 5,
    long_change_days: int = 20,
) -> pd.DataFrame:
    """Point-in-time **relative** volatility changes over short and long horizons.

    Each change is ``current / value_n_ago - 1`` (``pct_change``), computed on the
    already-lagged series so it introduces no look-ahead. Division by a zero prior
    value yields ``NaN`` (not ``inf``). Returns a frame aligned to ``vol_series``
    with columns ``change_{short}d`` and ``change_{long}d``.
    """
    short = vol_series.pct_change(periods=short_change_days, fill_method=None)
    long = vol_series.pct_change(periods=long_change_days, fill_method=None)
    return pd.DataFrame(
        {
            f"change_{short_change_days}d": short.replace([np.inf, -np.inf], np.nan),
            f"change_{long_change_days}d": long.replace([np.inf, -np.inf], np.nan),
        }
    )


def compute_volatility_term_ratio(short_vol: pd.Series, long_vol: pd.Series) -> pd.Series:
    """``short_vol / long_vol`` (rolling_20 / rolling_60), division-by-zero safe -> ``NaN``."""
    ratio = short_vol / long_vol
    return ratio.replace([np.inf, -np.inf], np.nan)


def classify_volatility_direction(
    relative_change: float | None,
    rising_threshold: float,
    falling_threshold: float,
) -> str:
    """Classify a relative change as ``Rising`` / ``Falling`` / ``Stable`` / ``Unknown``.

    Deterministic boundaries: ``>= rising_threshold`` is Rising, ``<= falling_threshold``
    is Falling (a value exactly on a threshold takes the directional label).
    """
    if relative_change is None:
        return "Unknown"
    x = float(relative_change)
    if math.isnan(x):
        return "Unknown"
    if x >= rising_threshold:
        return "Rising"
    if x <= falling_threshold:
        return "Falling"
    return "Stable"


def classify_volatility_term_state(
    ratio: float | None,
    expansion_threshold: float,
    contraction_threshold: float,
) -> str:
    """Classify a 20D/60D ratio as ``Expansion`` / ``Contraction`` / ``Balanced`` / ``Unknown``.

    Deterministic boundaries: ``>= expansion_threshold`` is Expansion,
    ``<= contraction_threshold`` is Contraction. A missing ratio (e.g. absent
    ``rolling_60``) is ``Unknown``.
    """
    if ratio is None:
        return "Unknown"
    x = float(ratio)
    if math.isnan(x):
        return "Unknown"
    if x >= expansion_threshold:
        return "Expansion"
    if x <= contraction_threshold:
        return "Contraction"
    return "Balanced"


def ratio_reference_lines(bands: dict[str, float] = VOL_RATIO_BANDS) -> list[float]:
    """Term-ratio chart guides, ascending ([0.85, 1.00, 1.15])."""
    return sorted({bands["contraction"], 1.0, bands["expansion"]})


def change_reference_lines(thresholds: dict[str, float] = VOL_DIRECTION_THRESHOLDS) -> list[float]:
    """Relative-change chart guides, ascending ([-0.10, 0.00, 0.10])."""
    return sorted({thresholds["falling"], 0.0, thresholds["rising"]})
