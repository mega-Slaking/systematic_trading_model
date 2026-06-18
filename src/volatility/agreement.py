"""Phase 4 — estimator agreement and disagreement.

Makes the spread *between* the five estimators measurable instead of eyeballed.
Agreement is classified from **both** a relative-dispersion threshold **and** an
absolute-spread floor — the floor is part of the real interface, not a footnote,
because SHY's ~1–2% volatility makes pure relative dispersion misleading (a
trivial 0.0012 spread on a 1.2% median is 25%+ relative but obviously *not*
disagreement).

All point-in-time, on the already-lagged surface columns (§4.1).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

UNKNOWN_AGREEMENT = "Unknown"


@dataclass(frozen=True)
class EstimatorAgreementConfig:
    """Relative + absolute thresholds for agreement classification (configurable)."""

    high_relative_threshold: float = 0.10      # relative_dispersion < this => High
    low_relative_threshold: float = 0.25       # relative gate for Low
    low_agreement_absolute_floor: float = 0.0025
    # 0.0025 == 0.25 annualised-vol percentage points, expressed in internal decimals.
    min_estimators: int = 3

    def version(self) -> str:
        """Stable 12-char hash of the fields for cache keys (§7.3)."""
        fields = (
            self.high_relative_threshold, self.low_relative_threshold,
            self.low_agreement_absolute_floor, self.min_estimators,
        )
        return hashlib.sha1(repr(fields).encode()).hexdigest()[:12]


def compute_estimator_dispersion(
    df: pd.DataFrame,
    estimator_columns: list[str],
    min_estimators: int,
) -> pd.DataFrame:
    """Point-in-time estimator-dispersion features per row.

    Returns a frame aligned to ``df`` with ``absolute_spread`` (max − min),
    ``relative_dispersion`` ((max − min) / median, division-by-zero safe),
    ``estimator_median``, ``highest_estimator`` / ``lowest_estimator`` (internal
    column names), and ``fast_premium`` (``rolling_20 / median(rolling_60,
    ewma_97, garch)``). Rows with fewer than ``min_estimators`` valid estimates
    have their dispersion outputs nulled (the fast premium is independent of that
    gate).
    """
    present = [c for c in estimator_columns if c in df.columns]
    sub = df[present]

    valid_count = sub.notna().sum(axis=1)
    row_max = sub.max(axis=1)
    row_min = sub.min(axis=1)
    row_median = sub.median(axis=1)
    absolute_spread = row_max - row_min
    relative_dispersion = (absolute_spread / row_median).replace([np.inf, -np.inf], np.nan)

    # idxmax/idxmin over an all-NaN row would warn; restrict to rows with >=1 valid.
    has_any = valid_count > 0
    highest = pd.Series(pd.NA, index=df.index, dtype=object)
    lowest = pd.Series(pd.NA, index=df.index, dtype=object)
    if has_any.any():
        highest.loc[has_any] = sub.loc[has_any].idxmax(axis=1)
        lowest.loc[has_any] = sub.loc[has_any].idxmin(axis=1)

    slow_cols = [c for c in ("rolling_60", "ewma_97", "garch") if c in df.columns]
    if "rolling_20" in df.columns and slow_cols:
        slow_median = df[slow_cols].median(axis=1)
        fast_premium = (df["rolling_20"] / slow_median).replace([np.inf, -np.inf], np.nan)
    else:
        fast_premium = pd.Series(np.nan, index=df.index)

    insufficient = valid_count < min_estimators
    keep = ~insufficient
    return pd.DataFrame(
        {
            "absolute_spread": absolute_spread.where(keep),
            "relative_dispersion": relative_dispersion.where(keep),
            "estimator_median": row_median.where(keep),
            "highest_estimator": highest.where(keep),
            "lowest_estimator": lowest.where(keep),
            "fast_premium": fast_premium,
        },
        index=df.index,
    )


def classify_estimator_agreement(
    relative_dispersion: float | None,
    absolute_spread: float | None,
    config: EstimatorAgreementConfig,
) -> str:
    """Classify agreement as High / Moderate / Low / Unknown.

    * **High:** ``relative_dispersion < high_relative_threshold``.
    * **Low:** only if **both** ``relative_dispersion > low_relative_threshold``
      **and** ``absolute_spread > low_agreement_absolute_floor`` (the floor stops
      a tiny-but-relatively-large SHY spread from reading as disagreement).
    * **Moderate:** otherwise.
    """
    if _missing(relative_dispersion) or _missing(absolute_spread):
        return UNKNOWN_AGREEMENT

    rd = float(relative_dispersion)
    asp = float(absolute_spread)

    if rd < config.high_relative_threshold:
        return "High"
    if rd > config.low_relative_threshold and asp > config.low_agreement_absolute_floor:
        return "Low"
    return "Moderate"


def _missing(value: float | None) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))
