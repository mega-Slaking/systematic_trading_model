"""Per-row point-in-time feature frame for one ticker (shared Phase 1–3 orchestration).

The canonical place that turns one ticker's already-lagged estimator history into
the per-row inputs every diagnostic state/table is assembled from: the historical
percentile (Phase 1), the 20D/60D term ratio and 5D/20D changes (Phase 2), and the
derived level / direction / term-state labels. Pure and UI-agnostic — the API
service wraps it with its TTL-cached percentile, and the Phase 10 snapshot builder
reuses it on a trailing as-of slice, so the two cannot drift apart.
"""

from __future__ import annotations

import pandas as pd

from src.volatility.direction import (
    classify_volatility_direction,
    classify_volatility_term_state,
    compute_volatility_direction_features,
    compute_volatility_term_ratio,
)
from src.volatility.percentiles import (
    classify_volatility_level,
    compute_rolling_percentile,
    percentile_to_ordinal,
)
from src.volatility.states import VolatilityStateConfig


def _term_ratio(history: pd.DataFrame) -> pd.Series:
    """``rolling_20 / rolling_60`` over the slice, or an all-NaN series if either is absent."""
    if {"rolling_20", "rolling_60"} <= set(history.columns):
        return compute_volatility_term_ratio(history["rolling_20"], history["rolling_60"])
    return pd.Series(float("nan"), index=history.index)


def build_ticker_feature_frame(
    history: pd.DataFrame,
    *,
    estimator: str,
    window: int | None,
    min_periods: int,
    config: VolatilityStateConfig,
    ticker: str | None = None,
    percentile: pd.Series | None = None,
) -> pd.DataFrame:
    """Per-row point-in-time features for one ticker's (already-lagged) history.

    ``history`` is one ticker's surface rows, sorted ascending by date. ``window`` is
    the resolved trailing length (``None`` => expanding "Full"); ``config`` supplies
    the level/direction/ratio thresholds so every consumer agrees on one source of
    truth. Pass a precomputed ``percentile`` series (e.g. the API's TTL-cached one)
    to reuse it; otherwise it is computed here via the canonical Phase 1 algorithm.

    Returns the columns ``compute_state_series`` / ``build_latest_volatility_state_table``
    expect: ``date, ticker, current_volatility, percentile, percentile_ordinal,
    volatility_level, change_5d, change_20d, term_ratio, term_state, direction``.
    """
    if percentile is None:
        percentile = compute_rolling_percentile(history[estimator], window, int(min_periods))
    changes = compute_volatility_direction_features(history[estimator])
    ratio = _term_ratio(history)

    pct_vals = percentile.to_numpy()
    ratio_vals = ratio.to_numpy()
    change_20 = changes["change_20d"].to_numpy()

    return pd.DataFrame(
        {
            "date": history["date"].to_numpy(),
            "ticker": ticker if ticker is not None else history.get("ticker"),
            "current_volatility": history[estimator].to_numpy(),
            "percentile": pct_vals,
            "percentile_ordinal": [percentile_to_ordinal(p) for p in pct_vals],
            "volatility_level": [classify_volatility_level(p, config.level_thresholds()) for p in pct_vals],
            "change_5d": changes["change_5d"].to_numpy(),
            "change_20d": change_20,
            "term_ratio": ratio_vals,
            "term_state": [
                classify_volatility_term_state(r, config.expansion_ratio, config.contraction_ratio)
                for r in ratio_vals
            ],
            "direction": [
                classify_volatility_direction(c, config.rising_change, config.falling_change)
                for c in change_20
            ],
        }
    )
