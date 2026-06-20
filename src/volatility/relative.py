"""Phase 7 — cross-asset relative volatility.

Shows whether one asset is becoming unusually risky **relative to the others**
the strategy chooses among (TLT/AGG/SHY), via point-in-time vol ratios and their
own historical percentiles. **Monitor only — never an allocation signal.**

Methodology caveat (surfaced in the UI): a ratio like TLT/SHY (~7×) trends with
the duration differential, so its "5Y percentile" is a single-path, trend-laden
statistic. Read "Elevated (74th)" as a monitor, not a tradable risk reading — the
same overlap/trend caveat as the Phase 2 term ratio.

All point-in-time on the already-lagged surface (§4.1); ratio percentiles reuse
the Phase 1 algorithm per pair and are cached on §7.4 cross-asset keys.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Preferred numerator-first ordering (higher duration first) so the canonical pairs
# read TLT/AGG, TLT/SHY, AGG/SHY rather than an arbitrary alphabetical order.
DURATION_ORDER = ["TLT", "AGG", "SHY"]


def default_ratio_pairs(tickers: list[str]) -> list[tuple[str, str]]:
    """Canonical ordered pairs over the present tickers (duration-ordered numerator)."""
    ordered = [t for t in DURATION_ORDER if t in tickers] + [t for t in tickers if t not in DURATION_ORDER]
    return [(ordered[i], ordered[j]) for i in range(len(ordered)) for j in range(i + 1, len(ordered))]


def compute_relative_volatility_ratios(
    wide_vol_df: pd.DataFrame,
    ratio_pairs: list[tuple[str, str]],
) -> pd.DataFrame:
    """Point-in-time cross-asset volatility ratios, one column per pair.

    ``wide_vol_df`` is date-indexed with one column per ticker (the reference
    estimator's vol). Each pair ``(a, b)`` becomes column ``"a/b" = vol_a / vol_b``,
    division-by-zero safe (``inf`` -> ``NaN``). Pairs whose tickers are absent are
    skipped. The reference estimator must be the same for every column (the caller's
    responsibility — that is why the input is a single wide frame).
    """
    out: dict[str, pd.Series] = {}
    for a, b in ratio_pairs:
        if a in wide_vol_df.columns and b in wide_vol_df.columns:
            ratio = wide_vol_df[a] / wide_vol_df[b]
            out[f"{a}/{b}"] = ratio.replace([np.inf, -np.inf], np.nan)
    return pd.DataFrame(out, index=wide_vol_df.index)


def build_cross_asset_risk_table(asset_rows: pd.DataFrame) -> pd.DataFrame:
    """Rank assets by **raw current volatility** (highest = rank 1).

    ``asset_rows`` carries one latest row per asset with at least
    ``current_volatility`` (plus the display columns ``ticker``,
    ``percentile_ordinal``, ``confirmed_state`` the caller wants ranked alongside).
    Raw magnitude only — TLT will essentially always outrank SHY by duration, so the
    percentile and confirmed state (kept in the row) carry the real relative context,
    not the rank itself.
    """
    if asset_rows.empty:
        return asset_rows.assign(rank=pd.Series(dtype=int)) if "rank" not in asset_rows else asset_rows
    ranked = asset_rows.sort_values(
        "current_volatility", ascending=False, na_position="last"
    ).reset_index(drop=True)
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    return ranked
