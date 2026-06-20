"""Volatility-features service (spec endpoints 8 + 9).

Wraps ``db_reader.get_volatility_features`` (the persisted, scenario-independent
surface) into per-ticker vol lines and the latest-per-ticker table.
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

import pandas as pd

from src.storage.db_reader import get_etf_history, get_volatility_features
from src.volatility.audit import surface_data_version, validate_volatility_surface
from src.volatility.constants import (
    CONFIG_KEY_COLUMN,
    DEFAULT_HISTORICAL_WINDOW,
    DEFAULT_REFERENCE_ESTIMATOR,
    HISTORICAL_WINDOWS,
    MIN_PERCENTILE_HISTORY,
    VOL_ESTIMATOR_COLUMNS,
    VOL_ESTIMATOR_NAMES,
)
from src.volatility.agreement import (
    EstimatorAgreementConfig,
    classify_estimator_agreement,
    compute_estimator_dispersion,
)
from src.volatility.outcomes import (
    COMBINED_CONDITIONS,
    COND_RELATIVE_VOL_EXTREME,
    DEFAULT_MIN_SAMPLE_GATES,
    FORWARD_HORIZONS,
    RECENT_PEAK_LOOKBACK,
    RELATIVE_EXTREME_PERCENTILE,
    OUTCOME_STATES,
    build_combined_condition_outcome_table,
    build_state_return_distribution,
    build_volatility_signal_outcome_table,
    compute_combined_condition_flags,
    compute_forward_asset_returns,
    compute_forward_window_drawdowns,
)
from src.volatility.direction import (
    VOL_DIRECTION_THRESHOLDS,
    VOL_RATIO_BANDS,
    change_reference_lines,
    compute_volatility_direction_features,
    compute_volatility_term_ratio,
    ratio_reference_lines,
)
from src.volatility.feature_frame import build_ticker_feature_frame
from src.volatility.models import VolatilityFeatureConfig, VolatilityFeatureSurface
from src.volatility.snapshot import VolatilitySignalSnapshotProvider
from src.volatility.percentiles import (
    classify_volatility_level,
    compute_rolling_percentile,
    level_reference_lines,
    percentile_to_ordinal,
)
from src.volatility.price_context import (
    PRICE_DIRECTION_THRESHOLD,
    classify_price_volatility_context,
    compute_price_direction_features,
)
from src.volatility.relative import (
    build_cross_asset_risk_table,
    compute_relative_volatility_ratios,
    default_ratio_pairs,
)
from src.volatility.stability import (
    classify_estimate_stability,
    compute_volatility_of_volatility,
    stability_reference_lines,
)
from src.volatility.states import (
    VolatilityStateConfig,
    build_latest_volatility_state_table,
    compute_state_series,
)
from src.volatility.transitions import (
    build_state_ranges,
    detect_persistent_state_transitions,
)

from api.cache import TTLCache
from api.config import get_settings
from api.schemas.volatility import (
    AssetRiskRankRow,
    CrossAssetRatioRow,
    CrossAssetRatioSeriesResponse,
    CrossAssetVolatilityResponse,
    EstimateStabilityResponse,
    EstimatorAgreementResponse,
    AssetRiskRankSnapshotRow,
    AssetVolatilitySnapshotResponse,
    CrossAssetRatioSnapshotRow,
    CrossAssetVolatilitySnapshotResponse,
    EstimatorComparisonRow,
    SignalOutcomeDistributionResponse,
    SignalOutcomeResponse,
    SignalOutcomeRow,
    StateReturnDistribution,
    VolatilityAuditResponse,
    VolatilityChartResponse,
    VolatilityContextResponse,
    VolatilityFeaturesResponse,
    VolatilityLatestResponse,
    VolatilityPercentileSeriesResponse,
    VolatilityPoint,
    VolatilityRatioChangeResponse,
    VolatilitySeries,
    VolatilityStateRange,
    VolatilityStateRow,
    VolatilityStateTableResponse,
    VolatilityTransition,
    VolLatestRow,
)

# Process-wide default configs (one source of truth for thresholds across phases).
_STATE_CONFIG = VolatilityStateConfig()
_AGREEMENT_CONFIG = EstimatorAgreementConfig()
from api.serialization.frames import df_to_series, nan_to_none, to_iso

# Raw annualized vol estimates in display order (mirrors the tab's _VOL_METHODS).
_VOL_METHODS: dict[str, str] = {
    "rolling_20": "Rolling 20d",
    "rolling_60": "Rolling 60d",
    "ewma_94": "EWMA λ=0.94",
    "ewma_97": "EWMA λ=0.97",
    "garch": "GARCH(1,1)",
}


def _clean_float(value: object) -> float | None:
    cleaned = nan_to_none(value)
    return float(cleaned) if isinstance(cleaned, (int, float)) and not isinstance(cleaned, bool) else None


def get_volatility_for_ticker(ticker: str, methods: list[str] | None = None) -> VolatilityFeaturesResponse:
    """Per-method vol lines for one ticker (endpoint 8)."""
    df = get_volatility_features([ticker])
    if df.empty:
        return VolatilityFeaturesResponse(ticker=ticker, series=[], available_methods=[])

    tdf = df.sort_values("date")
    available = [m for m in _VOL_METHODS if m in tdf.columns and tdf[m].notna().any()]
    requested = [m for m in (methods or available) if m in available]

    series = [
        df_to_series(tdf, name=_VOL_METHODS[m], x="date", y=m, meta={"method": m})
        for m in requested
    ]
    return VolatilityFeaturesResponse(ticker=ticker, series=series, available_methods=available)


def get_volatility_latest() -> VolatilityLatestResponse:
    """Latest annualized vol per method per ticker (endpoint 9)."""
    methods = list(_VOL_METHODS)
    df = get_volatility_features()
    if df.empty:
        return VolatilityLatestResponse(methods=methods, rows=[])

    latest = df.sort_values("date").groupby("ticker").tail(1).sort_values("ticker")
    rows = [
        VolLatestRow(
            ticker=str(row["ticker"]),
            date=str(row["date"].date()) if pd.notna(row["date"]) else None,
            rolling_20=_clean_float(row.get("rolling_20")),
            rolling_60=_clean_float(row.get("rolling_60")),
            ewma_94=_clean_float(row.get("ewma_94")),
            ewma_97=_clean_float(row.get("ewma_97")),
            garch=_clean_float(row.get("garch")),
        )
        for _, row in latest.iterrows()
    ]
    return VolatilityLatestResponse(methods=methods, rows=rows)


def get_volatility_audit() -> VolatilityAuditResponse:
    """Phase 0 data-contract warnings for the persisted surface (diagnostic).

    Read-only: runs ``validate_volatility_surface`` over the whole persisted
    surface and reports the warnings plus the audited config_keys/row count.
    Never raises on data content, so it cannot break the page.
    """
    df = get_volatility_features()
    warnings = validate_volatility_surface(df, VOL_ESTIMATOR_NAMES)
    if CONFIG_KEY_COLUMN in df.columns:
        config_keys = [str(c) for c in sorted(df[CONFIG_KEY_COLUMN].dropna().unique())]
    else:
        config_keys = []
    return VolatilityAuditResponse(warnings=warnings, config_keys=config_keys, n_rows=int(len(df)))


# --------------------------------------------------------------------------- #
# Phase 1 — historical percentiles
# --------------------------------------------------------------------------- #

_percentile_cache: TTLCache | None = None


def _pct_cache() -> TTLCache:
    """Process-wide percentile cache (lazily built with the compute-cache TTL)."""
    global _percentile_cache
    if _percentile_cache is None:
        _percentile_cache = TTLCache(get_settings().tearsheet_cache_ttl_seconds)
    return _percentile_cache


def flush_cache() -> None:
    """Drop cached percentile frames (invalidation hook the backtest job calls, §7.5)."""
    _pct_cache().flush()


def _resolve_window(window_key: str) -> int | None:
    """Map a window key to a trailing length; ``"Full"`` -> ``None`` (expanding)."""
    if window_key == "Full":
        return None
    if window_key in HISTORICAL_WINDOWS:
        return HISTORICAL_WINDOWS[window_key]
    raise ValueError(f"unknown historical window '{window_key}'")


def _validate_estimator(estimator: str) -> None:
    if estimator not in VOL_ESTIMATOR_NAMES:
        raise ValueError(f"unknown estimator '{estimator}'")


def _single_config_slice(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Return ``(slice, config_key)`` for a single config (§4.3 isolation).

    The persisted surface is one config_key in practice; if drift ever produced
    several, pick the one with the latest data deterministically rather than
    mixing configs into one percentile series.
    """
    if CONFIG_KEY_COLUMN not in df.columns:
        return df, ""
    keys = df[CONFIG_KEY_COLUMN].dropna().unique()
    if len(keys) <= 1:
        return df, (str(keys[0]) if len(keys) else "")
    chosen = (
        df.dropna(subset=[CONFIG_KEY_COLUMN])
        .groupby(CONFIG_KEY_COLUMN)["date"]
        .max()
        .sort_values()
        .index[-1]
    )
    return df[df[CONFIG_KEY_COLUMN] == chosen].copy(), str(chosen)


def _load_ticker_ordered(ticker: str) -> tuple[pd.DataFrame, str]:
    """Return ``(surface_slice_sorted_by_date, config_key)`` for one ticker.

    A single-``config_key`` slice (§4.3) carrying every persisted column (the raw
    estimators + comparison features), sorted ascending by date. Empty frame +
    ``""`` when the ticker has no rows.
    """
    raw = get_volatility_features([ticker])
    if raw.empty:
        return raw, ""
    df_slice, config_key = _single_config_slice(raw)
    return df_slice.sort_values("date").reset_index(drop=True), config_key


def _percentile_series_cached(
    ordered: pd.DataFrame,
    config_key: str,
    ticker: str,
    estimator: str,
    window_key: str,
    min_periods: int,
) -> pd.Series:
    """Point-in-time percentile of ``ordered[estimator]``, cached on the §7.1 key.

    The key carries the feature id/version, config_key, ticker, estimator, window,
    min_periods and the surface ``data_version`` so a freshly persisted row
    invalidates a stale result before the TTL expires.
    """
    data_version = surface_data_version(ordered)
    key = (
        "vol_percentile", "v1", config_key, ticker, estimator, window_key,
        int(min_periods), data_version,
    )
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    percentile = compute_rolling_percentile(ordered[estimator], _resolve_window(window_key), int(min_periods))
    cache.set(key, percentile)
    return percentile


def _term_ratio_series(ordered: pd.DataFrame) -> pd.Series:
    """``rolling_20 / rolling_60`` over the slice, or an all-NaN series if either is absent."""
    if "rolling_20" in ordered.columns and "rolling_60" in ordered.columns:
        return compute_volatility_term_ratio(ordered["rolling_20"], ordered["rolling_60"])
    return pd.Series(float("nan"), index=ordered.index)


def _stability_series(
    ordered: pd.DataFrame,
    config_key: str,
    ticker: str,
    estimator: str,
    window_key: str,
    min_periods: int,
) -> tuple[pd.Series, pd.Series]:
    """``(vov_percentile_series, raw_vov_series)`` for the reference estimator, cached.

    The raw vol-of-vol is the 20D std of daily changes in the annualised vol; its
    percentile (the headline) reuses the Phase 1 algorithm over the chosen window.
    """
    data_version = surface_data_version(ordered)
    key = ("vol_stability", "v1", config_key, ticker, estimator, window_key, int(min_periods), data_version)
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    vov = compute_volatility_of_volatility(ordered[estimator], window=20)
    percentile = compute_rolling_percentile(vov, _resolve_window(window_key), int(min_periods))
    cache.set(key, (percentile, vov))
    return percentile, vov


def _features_frame(
    ordered: pd.DataFrame,
    config_key: str,
    ticker: str,
    estimator: str,
    window_key: str,
    min_periods: int,
) -> pd.DataFrame:
    """Per-row point-in-time features for one ticker — the inputs every Phase 1–3
    response is assembled from. The percentile is TTL-cached here (§7.1); the rest
    of the orchestration lives in the shared pure ``build_ticker_feature_frame`` so
    the API and the Phase 10 snapshot stay in lock-step on a single source of
    thresholds.
    """
    percentile = _percentile_series_cached(ordered, config_key, ticker, estimator, window_key, min_periods)
    return build_ticker_feature_frame(
        ordered,
        estimator=estimator,
        window=_resolve_window(window_key),
        min_periods=min_periods,
        config=_STATE_CONFIG,
        ticker=ticker,
        percentile=percentile,
    )


def _iso_date(value: object) -> str | None:
    """Scalar date -> ISO ``YYYY-MM-DD`` (or ``None`` for missing)."""
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _price_return_20d(prices_for_ticker: pd.DataFrame) -> pd.Series:
    """As-of-(t-1) 20-day price return for one ticker, indexed by date.

    Uses the ffilled close (consistent with how the surface treats prices), so a
    one-off missing close does not spuriously null the return.
    """
    if prices_for_ticker.empty or "close" not in prices_for_ticker.columns:
        return pd.Series(dtype=float)
    close = prices_for_ticker.sort_values("date").set_index("date")["close"].ffill()
    return compute_price_direction_features(close, horizons=(20,))["price_return_20d"]


def _insufficient_context(ticker: str, estimator: str, window_key: str, config_key: str) -> VolatilityContextResponse:
    return VolatilityContextResponse(
        ticker=ticker, config_key=config_key, reference_estimator=estimator,
        historical_window=window_key, as_of_date=None, information_through_date=None,
        current_volatility=None, historical_percentile=None, percentile_ordinal=None,
        volatility_level=classify_volatility_level(None), insufficient_history=True,
        direction="Unknown", change_5d=None, change_20d=None, term_ratio=None, term_state="Unknown",
        instantaneous_state="Unknown", confirmed_state="Unknown",
        state_explanation="Insufficient history to classify the volatility state.",
        state_config_version=_STATE_CONFIG.version(),
        estimator_agreement="Unknown", absolute_spread=None, relative_dispersion=None,
        agreement_config_version=_AGREEMENT_CONFIG.version(),
        price_volatility_context="Unknown", asset_return_20d=None, vol_change_20d=None,
    )


def get_volatility_context(
    ticker: str,
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> VolatilityContextResponse:
    """Latest level + direction + diagnostic state for one ticker (Phases 1–3).

    Cached on the §7.2 state key (adds the state-config version + confirmation policy
    to the §7.1 inputs) so a threshold change or a freshly persisted row both
    invalidate the result.
    """
    _validate_estimator(estimator)
    _resolve_window(window_key)  # validate early -> 422

    ordered, config_key = _load_ticker_ordered(ticker)
    if ordered.empty or estimator not in ordered.columns:
        return _insufficient_context(ticker, estimator, window_key, config_key)

    data_version = surface_data_version(ordered)
    key = (
        "vol_context", "v1", config_key, ticker, estimator, window_key, int(min_periods),
        _STATE_CONFIG.version(), int(_STATE_CONFIG.confirmation_days),
        _AGREEMENT_CONFIG.version(), PRICE_DIRECTION_THRESHOLD, data_version,
    )
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    feats = _features_frame(ordered, config_key, ticker, estimator, window_key, min_periods)
    state = build_latest_volatility_state_table(feats, feats["date"].max(), _STATE_CONFIG).iloc[0]

    # Estimator agreement at the latest date (across all five estimators).
    dispersion_last = compute_estimator_dispersion(
        ordered, VOL_ESTIMATOR_NAMES, _AGREEMENT_CONFIG.min_estimators
    ).iloc[-1]
    absolute_spread = _clean_float(dispersion_last["absolute_spread"])
    relative_dispersion = _clean_float(dispersion_last["relative_dispersion"])

    last = feats.iloc[-1]
    percentile = _clean_float(last["percentile"])
    prev_date = ordered["date"].iloc[-2] if len(ordered) >= 2 else None

    # Price/volatility context: as-of-(t-1) 20D price return + the 20D vol change.
    price_returns = _price_return_20d(get_etf_history([ticker]))
    asset_return_20d = _clean_float(price_returns.iloc[-1]) if not price_returns.empty else None
    vol_change_20d = _clean_float(last["change_20d"])
    price_volatility_context = classify_price_volatility_context(
        asset_return_20d, vol_change_20d, PRICE_DIRECTION_THRESHOLD, _STATE_CONFIG.rising_change
    )
    response = VolatilityContextResponse(
        ticker=ticker,
        config_key=config_key,
        reference_estimator=estimator,
        historical_window=window_key,
        as_of_date=_iso_date(last["date"]),
        information_through_date=_iso_date(prev_date),
        current_volatility=_clean_float(last["current_volatility"]),
        historical_percentile=percentile,
        percentile_ordinal=percentile_to_ordinal(percentile),
        volatility_level=str(last["volatility_level"]),
        insufficient_history=percentile is None,
        direction=str(last["direction"]),
        change_5d=_clean_float(last["change_5d"]),
        change_20d=_clean_float(last["change_20d"]),
        term_ratio=_clean_float(last["term_ratio"]),
        term_state=str(last["term_state"]),
        instantaneous_state=str(state["instantaneous_state"]),
        confirmed_state=str(state["confirmed_state"]),
        state_explanation=str(state["state_explanation"]),
        state_config_version=_STATE_CONFIG.version(),
        estimator_agreement=classify_estimator_agreement(
            relative_dispersion, absolute_spread, _AGREEMENT_CONFIG
        ),
        absolute_spread=absolute_spread,
        relative_dispersion=relative_dispersion,
        agreement_config_version=_AGREEMENT_CONFIG.version(),
        price_volatility_context=price_volatility_context,
        asset_return_20d=asset_return_20d,
        vol_change_20d=vol_change_20d,
    )
    cache.set(key, response)
    return response


def get_volatility_percentile_series(
    ticker: str,
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> VolatilityPercentileSeriesResponse:
    """The 0.0–1.0 historical-percentile line for one ticker/estimator/window."""
    _validate_estimator(estimator)
    _resolve_window(window_key)

    ordered, config_key = _load_ticker_ordered(ticker)
    if ordered.empty or estimator not in ordered.columns:
        return VolatilityPercentileSeriesResponse(
            ticker=ticker, config_key=config_key, reference_estimator=estimator,
            historical_window=window_key, series=[], reference_lines=level_reference_lines(),
        )

    percentile = _percentile_series_cached(ordered, config_key, ticker, estimator, window_key, min_periods)
    frame = pd.DataFrame({"date": ordered["date"], "percentile": percentile})
    label = f"{VOL_ESTIMATOR_COLUMNS.get(estimator, estimator)} percentile ({window_key})"
    return VolatilityPercentileSeriesResponse(
        ticker=ticker,
        config_key=config_key,
        reference_estimator=estimator,
        historical_window=window_key,
        series=[df_to_series(frame, name=label, x="date", y="percentile",
                             meta={"method": estimator, "window": window_key})],
        reference_lines=level_reference_lines(),
    )


# --------------------------------------------------------------------------- #
# Phase 2 — direction + term ratio series
# --------------------------------------------------------------------------- #


def get_volatility_derived(
    ticker: str,
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    view: str = "ratio",
) -> VolatilityRatioChangeResponse:
    """Term-ratio (``"ratio"``), volatility-change (``"change"``) or estimator-dispersion (``"dispersion"``) line."""
    if view not in {"ratio", "change", "dispersion"}:
        raise ValueError(f"unknown view '{view}' (expected 'ratio', 'change' or 'dispersion')")
    _validate_estimator(estimator)

    ordered, config_key = _load_ticker_ordered(ticker)

    def _empty(unit: str, reference_lines: list[float]) -> VolatilityRatioChangeResponse:
        return VolatilityRatioChangeResponse(
            ticker=ticker, config_key=config_key, reference_estimator=estimator,
            view=view, unit=unit, series=[], reference_lines=reference_lines,
        )

    if view == "dispersion":
        # Estimator-agnostic: relative dispersion across all five estimators, with the
        # High/Low agreement thresholds as guides.
        agreement_lines = [
            _AGREEMENT_CONFIG.high_relative_threshold, _AGREEMENT_CONFIG.low_relative_threshold,
        ]
        if ordered.empty:
            return _empty("ratio", agreement_lines)
        dispersion = compute_estimator_dispersion(
            ordered, VOL_ESTIMATOR_NAMES, _AGREEMENT_CONFIG.min_estimators
        )
        frame = pd.DataFrame({"date": ordered["date"], "dispersion": dispersion["relative_dispersion"]})
        series = [df_to_series(frame, name="Estimator dispersion", x="date", y="dispersion",
                               meta={"view": "dispersion"})]
        return VolatilityRatioChangeResponse(
            ticker=ticker, config_key=config_key, reference_estimator=estimator,
            view="dispersion", unit="ratio", series=series, reference_lines=agreement_lines,
        )

    if view == "ratio":
        if ordered.empty:
            return _empty("ratio", ratio_reference_lines())
        frame = pd.DataFrame({"date": ordered["date"], "ratio": _term_ratio_series(ordered)})
        series = [df_to_series(frame, name="20D / 60D ratio", x="date", y="ratio",
                               meta={"view": "ratio"})]
        return VolatilityRatioChangeResponse(
            ticker=ticker, config_key=config_key, reference_estimator=estimator,
            view="ratio", unit="ratio", series=series, reference_lines=ratio_reference_lines(),
        )

    # view == "change"
    if ordered.empty or estimator not in ordered.columns:
        return _empty("relative_change", change_reference_lines())
    changes = compute_volatility_direction_features(ordered[estimator])
    frame = pd.DataFrame(
        {"date": ordered["date"], "change_20d": changes["change_20d"], "change_5d": changes["change_5d"]}
    )
    series = [
        df_to_series(frame, name="20-day change", x="date", y="change_20d", meta={"view": "change", "horizon": 20}),
        df_to_series(frame, name="5-day change", x="date", y="change_5d", meta={"view": "change", "horizon": 5}),
    ]
    return VolatilityRatioChangeResponse(
        ticker=ticker, config_key=config_key, reference_estimator=estimator,
        view="change", unit="relative_change", series=series, reference_lines=change_reference_lines(),
    )


# --------------------------------------------------------------------------- #
# Phase 3 — all-asset confirmed-state table
# --------------------------------------------------------------------------- #


def _clean_ordinal(value: object) -> int | None:
    return int(value) if value is not None and not pd.isna(value) else None


def get_volatility_state_table(
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> VolatilityStateTableResponse:
    """Latest confirmed diagnostic state across all assets (cached on the §7.2 key)."""
    _validate_estimator(estimator)
    _resolve_window(window_key)

    raw = get_volatility_features()
    if raw.empty:
        return VolatilityStateTableResponse(
            as_of_date=None, config_key="", reference_estimator=estimator,
            state_config_version=_STATE_CONFIG.version(), rows=[],
        )

    df_slice, config_key = _single_config_slice(raw)
    data_version = surface_data_version(df_slice)
    tickers = sorted(str(t) for t in df_slice["ticker"].dropna().unique())
    key = (
        "vol_state_table", "v1", config_key, tuple(tickers), estimator, window_key,
        int(min_periods), _STATE_CONFIG.version(), int(_STATE_CONFIG.confirmation_days),
        PRICE_DIRECTION_THRESHOLD, data_version,
    )
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    frames = [
        _features_frame(
            df_slice[df_slice["ticker"] == t].sort_values("date").reset_index(drop=True),
            config_key, t, estimator, window_key, min_periods,
        )
        for t in tickers
        if estimator in df_slice.columns
    ]
    if not frames:
        return VolatilityStateTableResponse(
            as_of_date=None, config_key=config_key, reference_estimator=estimator,
            state_config_version=_STATE_CONFIG.version(), rows=[],
        )

    feats = pd.concat(frames, ignore_index=True)
    as_of = feats["date"].max()
    table = build_latest_volatility_state_table(feats, as_of, _STATE_CONFIG)

    # As-of-(t-1) 20D price return per ticker for the joint price/vol context.
    prices_all = get_etf_history(tickers)
    price_ret = {
        str(t): (lambda pr: _clean_float(pr.iloc[-1]) if not pr.empty else None)(_price_return_20d(grp))
        for t, grp in prices_all.groupby("ticker")
    }

    # Estimate-stability percentile per ticker.
    stability_pct: dict[str, float | None] = {}
    for t in tickers:
        if estimator not in df_slice.columns:
            continue
        ot = df_slice[df_slice["ticker"] == t].sort_values("date").reset_index(drop=True)
        pct, _ = _stability_series(ot, config_key, t, estimator, window_key, min_periods)
        stability_pct[t] = _clean_float(pct.iloc[-1]) if len(pct) else None

    rows = []
    for _, r in table.iterrows():
        ticker = str(r["ticker"])
        asset_return_20d = price_ret.get(ticker)
        sp = stability_pct.get(ticker)
        rows.append(
            VolatilityStateRow(
                ticker=ticker,
                confirmed_state=str(r["confirmed_state"]),
                percentile_ordinal=_clean_ordinal(r["percentile_ordinal"]),
                current_volatility=_clean_float(r["current_volatility"]),
                change_20d=_clean_float(r["change_20d"]),
                term_ratio=_clean_float(r["term_ratio"]),
                term_state=str(r["term_state"]),
                price_volatility_context=classify_price_volatility_context(
                    asset_return_20d, _clean_float(r["change_20d"]),
                    PRICE_DIRECTION_THRESHOLD, _STATE_CONFIG.rising_change,
                ),
                asset_return_20d=asset_return_20d,
                estimate_stability=classify_estimate_stability(sp),
                stability_percentile=sp,
            )
        )
    response = VolatilityStateTableResponse(
        as_of_date=_iso_date(as_of), config_key=config_key, reference_estimator=estimator,
        state_config_version=_STATE_CONFIG.version(), rows=rows,
    )
    cache.set(key, response)
    return response


# --------------------------------------------------------------------------- #
# Phase 4 — estimator-agreement comparison panel
# --------------------------------------------------------------------------- #


def _label(method: str) -> str:
    return VOL_ESTIMATOR_COLUMNS.get(method, method)


def get_estimator_agreement(
    ticker: str,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> EstimatorAgreementResponse:
    """Estimator-agreement summary + per-estimator comparison panel (cached on the §7.3 key)."""
    _resolve_window(window_key)

    ordered, config_key = _load_ticker_ordered(ticker)
    if ordered.empty:
        return EstimatorAgreementResponse(
            ticker=ticker, config_key=config_key, agreement="Unknown",
            absolute_spread=None, relative_dispersion=None, highest_estimator=None,
            lowest_estimator=None, agreement_config_version=_AGREEMENT_CONFIG.version(), rows=[],
        )

    present = [c for c in VOL_ESTIMATOR_NAMES if c in ordered.columns]
    data_version = surface_data_version(ordered)
    key = (
        "estimator_agreement", "v1", config_key, ticker, tuple(present), window_key,
        int(min_periods), _AGREEMENT_CONFIG.min_estimators, _AGREEMENT_CONFIG.version(), data_version,
    )
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    dispersion = compute_estimator_dispersion(
        ordered, VOL_ESTIMATOR_NAMES, _AGREEMENT_CONFIG.min_estimators
    ).iloc[-1]
    absolute_spread = _clean_float(dispersion["absolute_spread"])
    relative_dispersion = _clean_float(dispersion["relative_dispersion"])
    median = _clean_float(dispersion["estimator_median"])
    highest = dispersion["highest_estimator"]
    lowest = dispersion["lowest_estimator"]

    rows: list[EstimatorComparisonRow] = []
    for method in present:
        current = _clean_float(ordered[method].iloc[-1])
        pct = _percentile_series_cached(ordered, config_key, ticker, method, window_key, min_periods)
        abs_diff = (current - median) if (current is not None and median is not None) else None
        rel_diff = (abs_diff / median) if (abs_diff is not None and median not in (None, 0)) else None
        rows.append(
            EstimatorComparisonRow(
                estimator=_label(method),
                method=method,
                current_volatility=current,
                historical_percentile_ordinal=percentile_to_ordinal(_clean_float(pct.iloc[-1])),
                absolute_diff_vs_median=abs_diff,
                relative_diff_vs_median=rel_diff,
            )
        )

    response = EstimatorAgreementResponse(
        ticker=ticker,
        config_key=config_key,
        agreement=classify_estimator_agreement(relative_dispersion, absolute_spread, _AGREEMENT_CONFIG),
        absolute_spread=absolute_spread,
        relative_dispersion=relative_dispersion,
        highest_estimator=_label(str(highest)) if highest is not None and not pd.isna(highest) else None,
        lowest_estimator=_label(str(lowest)) if lowest is not None and not pd.isna(lowest) else None,
        agreement_config_version=_AGREEMENT_CONFIG.version(),
        rows=rows,
    )
    cache.set(key, response)
    return response


# --------------------------------------------------------------------------- #
# Phase 6 — unified typed chart payload (series + shading + transitions)
# --------------------------------------------------------------------------- #

_CHART_VIEWS = {"volatility", "percentile", "ratio", "change", "dispersion", "vov"}
_TRANSITION_COOLDOWN_DAYS = 10


def _vseries(name: str, method: str | None, unit: str, dates: pd.Series, values) -> VolatilitySeries:
    iso = to_iso(dates).tolist()
    points = [VolatilityPoint(date=d, value=_clean_float(v)) for d, v in zip(iso, values)]
    return VolatilitySeries(name=name, method=method, unit=unit, points=points)


def _chart_series(ordered: pd.DataFrame, estimator: str, window_key: str, min_periods: int, view: str,
                  config_key: str, ticker: str) -> tuple[list[VolatilitySeries], str, list[float]]:
    """Build (series, unit, reference_lines) for one chart view."""
    dates = ordered["date"]

    if view == "volatility":
        present = [c for c in VOL_ESTIMATOR_NAMES if c in ordered.columns]
        series = [_vseries(_label(m), m, "decimal", dates, ordered[m]) for m in present]
        return series, "decimal", []

    if view == "percentile":
        pct = _percentile_series_cached(ordered, config_key, ticker, estimator, window_key, min_periods)
        name = f"{_label(estimator)} percentile ({window_key})"
        return [_vseries(name, estimator, "percentile", dates, pct)], "percentile", level_reference_lines()

    if view == "ratio":
        return (
            [_vseries("20D / 60D ratio", None, "ratio", dates, _term_ratio_series(ordered))],
            "ratio",
            ratio_reference_lines(),
        )

    if view == "change":
        changes = compute_volatility_direction_features(ordered[estimator])
        series = [
            _vseries("20-day change", estimator, "decimal_change", dates, changes["change_20d"]),
            _vseries("5-day change", estimator, "decimal_change", dates, changes["change_5d"]),
        ]
        return series, "decimal_change", change_reference_lines()

    if view == "vov":
        # Estimate stability: the vol-of-vol *percentile* (the raw value is muddy units).
        percentile, _ = _stability_series(ordered, config_key, ticker, estimator, window_key, min_periods)
        name = f"{_label(estimator)} estimate stability ({window_key})"
        return [_vseries(name, estimator, "percentile", dates, percentile)], "percentile", stability_reference_lines()

    # dispersion
    dispersion = compute_estimator_dispersion(ordered, VOL_ESTIMATOR_NAMES, _AGREEMENT_CONFIG.min_estimators)
    agreement_lines = [_AGREEMENT_CONFIG.high_relative_threshold, _AGREEMENT_CONFIG.low_relative_threshold]
    return (
        [_vseries("Estimator dispersion", None, "ratio", dates, dispersion["relative_dispersion"])],
        "ratio",
        agreement_lines,
    )


def get_volatility_chart(
    ticker: str,
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    view: str = "volatility",
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> VolatilityChartResponse:
    """Unified typed chart payload for ``view`` + confirmed-state shading + transitions.

    Returns ``series`` (per-view traces), ``state_ranges`` (confirmed-state bands),
    ``transitions`` (cooldown-gated markers), ``reference_lines`` and ``unit``.
    Cached on the §7.2 key (view + state/agreement versions + data_version).
    """
    if view not in _CHART_VIEWS:
        raise ValueError(f"unknown view '{view}' (expected one of {sorted(_CHART_VIEWS)})")
    _validate_estimator(estimator)
    _resolve_window(window_key)

    ordered, config_key = _load_ticker_ordered(ticker)
    if ordered.empty or estimator not in ordered.columns:
        return VolatilityChartResponse(
            ticker=ticker, config_key=config_key, view_mode=view, unit="decimal",
            as_of_date=None, series=[], state_ranges=[], transitions=[], reference_lines=[],
        )

    data_version = surface_data_version(ordered)
    key = (
        "vol_chart", "v1", config_key, ticker, estimator, window_key, int(min_periods), view,
        _STATE_CONFIG.version(), int(_STATE_CONFIG.confirmation_days), _TRANSITION_COOLDOWN_DAYS,
        _AGREEMENT_CONFIG.version(), data_version,
    )
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    series, unit, reference_lines = _chart_series(
        ordered, estimator, window_key, min_periods, view, config_key, ticker
    )

    # Confirmed-state shading + transitions (same reference estimator/window as the view).
    feats = _features_frame(ordered, config_key, ticker, estimator, window_key, min_periods)
    _, confirmed = compute_state_series(feats, _STATE_CONFIG)
    confirmed_by_date = pd.Series(confirmed.to_numpy(), index=pd.to_datetime(feats["date"]))
    ranges = build_state_ranges(confirmed_by_date)
    transitions = detect_persistent_state_transitions(
        confirmed_by_date, _STATE_CONFIG.confirmation_days, _TRANSITION_COOLDOWN_DAYS
    )

    state_ranges = [
        VolatilityStateRange(start=_iso_date(r["start"]), end=_iso_date(r["end"]), state=str(r["state"]))
        for _, r in ranges.iterrows()
    ]
    transition_models = [
        VolatilityTransition(
            date=_iso_date(t["date"]), kind=str(t["kind"]),
            from_state=(None if pd.isna(t["from_state"]) else str(t["from_state"])),
            to_state=(None if pd.isna(t["to_state"]) else str(t["to_state"])),
            label=str(t["label"]),
        )
        for _, t in transitions.iterrows()
    ]

    response = VolatilityChartResponse(
        ticker=ticker,
        config_key=config_key,
        view_mode=view,
        unit=unit,
        as_of_date=_iso_date(ordered["date"].iloc[-1]),
        series=series,
        state_ranges=state_ranges,
        transitions=transition_models,
        reference_lines=reference_lines,
    )
    cache.set(key, response)
    return response


# --------------------------------------------------------------------------- #
# Phase 7 — cross-asset relative volatility (monitor only)
# --------------------------------------------------------------------------- #


def _wide_vol(df_slice: pd.DataFrame, estimator: str) -> pd.DataFrame:
    """date × ticker frame of the reference estimator's vol (consistent estimator)."""
    return df_slice.pivot_table(index="date", columns="ticker", values=estimator).sort_index()


def get_cross_asset_volatility(
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> CrossAssetVolatilityResponse:
    """Per-pair relative-vol ratios (+ own percentile) and the all-asset risk ranking.

    Monitor only — the ranking is by **raw** current vol; percentile + confirmed
    state carry the real relative context. Cached on the §7.4 cross-asset key.
    """
    _validate_estimator(estimator)
    _resolve_window(window_key)

    raw = get_volatility_features()
    if raw.empty or estimator not in raw.columns:
        return CrossAssetVolatilityResponse(
            as_of_date=None, config_key="", reference_estimator=estimator, ratios=[], ranking=[],
        )

    df_slice, config_key = _single_config_slice(raw)
    data_version = surface_data_version(df_slice)
    tickers = sorted(str(t) for t in df_slice["ticker"].dropna().unique())
    key = ("relative_vol", "v1", config_key, tuple(tickers), estimator, window_key, int(min_periods), data_version)
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    wide = _wide_vol(df_slice, estimator)
    pairs = default_ratio_pairs(tickers)
    ratios_df = compute_relative_volatility_ratios(wide, pairs)
    as_of = wide.index.max() if len(wide.index) else None

    ratio_rows: list[CrossAssetRatioRow] = []
    for a, b in pairs:
        col = f"{a}/{b}"
        if col not in ratios_df.columns:
            continue
        pct = _clean_float(
            compute_rolling_percentile(ratios_df[col], _resolve_window(window_key), int(min_periods)).iloc[-1]
        )
        ratio_rows.append(
            CrossAssetRatioRow(
                pair=f"{a} / {b}",
                current_ratio=_clean_float(ratios_df[col].iloc[-1]),
                percentile_ordinal=percentile_to_ordinal(pct),
                relative_risk_state=classify_volatility_level(pct),
            )
        )

    # Ranking reuses the confirmed-state table (one latest row per asset).
    table = get_volatility_state_table(estimator, window_key, min_periods)
    rank_src = pd.DataFrame(
        [
            {"ticker": r.ticker, "current_volatility": r.current_volatility,
             "percentile_ordinal": r.percentile_ordinal, "confirmed_state": r.confirmed_state}
            for r in table.rows
        ]
    )
    ranking: list[AssetRiskRankRow] = []
    if not rank_src.empty:
        for _, r in build_cross_asset_risk_table(rank_src).iterrows():
            ranking.append(
                AssetRiskRankRow(
                    rank=int(r["rank"]),
                    ticker=str(r["ticker"]),
                    current_volatility=_clean_float(r["current_volatility"]),
                    percentile_ordinal=_clean_ordinal(r["percentile_ordinal"]),
                    confirmed_state=str(r["confirmed_state"]),
                )
            )

    response = CrossAssetVolatilityResponse(
        as_of_date=_iso_date(as_of), config_key=config_key, reference_estimator=estimator,
        ratios=ratio_rows, ranking=ranking,
    )
    cache.set(key, response)
    return response


def get_cross_asset_ratio_series(
    pair: str,
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    view: str = "raw",
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> CrossAssetRatioSeriesResponse:
    """One pair's ratio over time (``view="raw"``) or its historical percentile (``view="percentile"``)."""
    if view not in {"raw", "percentile"}:
        raise ValueError(f"unknown view '{view}' (expected 'raw' or 'percentile')")
    _validate_estimator(estimator)
    _resolve_window(window_key)
    parts = [p.strip().upper() for p in pair.split("/")]
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"pair must be 'A/B', got {pair!r}")
    a, b = parts
    label = f"{a} / {b}"
    unit = "percentile" if view == "percentile" else "ratio"
    ref_lines = level_reference_lines() if view == "percentile" else []

    def _empty(config_key: str = "") -> CrossAssetRatioSeriesResponse:
        return CrossAssetRatioSeriesResponse(
            pair=label, config_key=config_key, reference_estimator=estimator,
            view=view, unit=unit, series=[], reference_lines=ref_lines,
        )

    raw_df = get_volatility_features([a, b])
    if raw_df.empty or estimator not in raw_df.columns:
        return _empty()

    df_slice, config_key = _single_config_slice(raw_df)
    ratios = compute_relative_volatility_ratios(_wide_vol(df_slice, estimator), [(a, b)])
    col = f"{a}/{b}"
    if col not in ratios.columns:
        return _empty(config_key)

    dates = pd.Series(ratios.index).to_numpy()
    if view == "percentile":
        values = compute_rolling_percentile(ratios[col], _resolve_window(window_key), int(min_periods)).to_numpy()
        name = f"{label} percentile"
    else:
        values = ratios[col].to_numpy()
        name = f"{label} ratio"

    frame = pd.DataFrame({"date": dates, "value": values})
    series = [df_to_series(frame, name=name, x="date", y="value", meta={"pair": label, "view": view})]
    return CrossAssetRatioSeriesResponse(
        pair=label, config_key=config_key, reference_estimator=estimator,
        view=view, unit=unit, series=series, reference_lines=ref_lines,
    )


# --------------------------------------------------------------------------- #
# Phase 8 — estimate stability (vol-of-vol)
# --------------------------------------------------------------------------- #


def get_estimate_stability(
    ticker: str,
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> EstimateStabilityResponse:
    """Vol-of-vol stability for one ticker: percentile + status headline, raw value for details."""
    _validate_estimator(estimator)
    _resolve_window(window_key)

    ordered, config_key = _load_ticker_ordered(ticker)
    if ordered.empty or estimator not in ordered.columns:
        return EstimateStabilityResponse(
            ticker=ticker, config_key=config_key, stability_percentile=None,
            percentile_ordinal=None, estimate_stability="Unknown",
            stability_window=window_key, raw_vol_of_vol=None,
        )

    percentile, vov = _stability_series(ordered, config_key, ticker, estimator, window_key, min_periods)
    sp = _clean_float(percentile.iloc[-1])
    return EstimateStabilityResponse(
        ticker=ticker,
        config_key=config_key,
        stability_percentile=sp,
        percentile_ordinal=percentile_to_ordinal(sp),
        estimate_stability=classify_estimate_stability(sp),
        stability_window=window_key,
        raw_vol_of_vol=_clean_float(vov.iloc[-1]),
    )


# --------------------------------------------------------------------------- #
# Phase 9 — historical signal outcome analysis
# --------------------------------------------------------------------------- #

# The standing caveat shown with every outcome table: outcomes describe what
# followed similar states *in this single sample*, not a causal or future claim.
_OUTCOME_DISCLAIMER = (
    "Outcomes describe what historically followed similar diagnostic states in "
    "this single sample. They do not establish causality and do not guarantee "
    "future performance. Non-overlapping sampling is the default because "
    "overlapping daily forward windows overstate the independent evidence."
)


def _forward_prices(prices_for_ticker: pd.DataFrame) -> pd.Series:
    """Unlagged, ffilled close indexed by date for one ticker (Phase 9 forward side).

    Uses the same ``close`` series the surface treats as its price column (§4.4),
    ffilled so a one-off missing close does not null an entire forward window.
    **Never shifted** — forward returns read prices strictly *after* the signal
    date; the as-of-``t`` convention lives entirely on the (already-lagged) state
    side of the join.
    """
    if prices_for_ticker.empty or "close" not in prices_for_ticker.columns:
        return pd.Series(dtype=float)
    return prices_for_ticker.sort_values("date").set_index("date")["close"].ffill()


def _forward_outcome_frame(ticker: str, with_drawdowns: bool = True) -> pd.DataFrame:
    """Unlagged forward returns (and optionally forward-window drawdowns) per date.

    The shared forward side of all three Phase 9 outcome endpoints: reads the
    UNLAGGED ffilled close strictly *after* each date (§Phase 9 alignment) and
    returns a ``date`` + ``forward_return_*`` (+ ``forward_max_drawdown_*``) frame,
    joined one-to-one. Empty (``columns=["date"]``) when the ticker has no price
    history, so callers branch on ``.empty``.
    """
    prices = _forward_prices(get_etf_history([ticker]))
    if prices.empty:
        return pd.DataFrame(columns=["date"])
    forward = compute_forward_asset_returns(prices, FORWARD_HORIZONS).reset_index(names="date")
    if with_drawdowns:
        drawdowns = compute_forward_window_drawdowns(prices, FORWARD_HORIZONS).reset_index(names="date")
        forward = forward.merge(drawdowns, on="date", how="inner", validate="one_to_one")
    return forward


def get_signal_outcomes(
    ticker: str,
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    sampling: str = "non_overlapping",
    start: str | None = None,
    end: str | None = None,
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> SignalOutcomeResponse:
    """Forward outcomes by confirmed diagnostic state for one ticker (Phase 9).

    The state side is the **already-lagged** confirmed-state series (as-of ``t``,
    info through ``t-1``); the forward side is the **unlagged** ffilled close read
    strictly *after* ``t``. They are joined one-to-one on date inside
    ``build_volatility_signal_outcome_table`` (which raises on any many-to-many
    key collision). Non-overlapping sampling is the default; ``sampling="all"``
    is the explicit, disclaimer-flagged override.

    Cached on the §7.2 state key extended with the horizon set, sampling mode and
    min-sample gates so a threshold/policy change or a freshly persisted row both
    invalidate the result.
    """
    if sampling not in {"non_overlapping", "all"}:
        raise ValueError(f"unknown sampling '{sampling}' (expected 'non_overlapping' or 'all')")
    _validate_estimator(estimator)
    _resolve_window(window_key)

    ordered, config_key = _load_ticker_ordered(ticker)
    horizon_labels = list(FORWARD_HORIZONS)
    if ordered.empty or estimator not in ordered.columns:
        return SignalOutcomeResponse(
            ticker=ticker, config_key=config_key, reference_estimator=estimator,
            sampling=sampling, horizons=horizon_labels, rows=[], disclaimer=_OUTCOME_DISCLAIMER,
        )

    data_version = surface_data_version(ordered)
    key = (
        "vol_outcomes", "v1", config_key, ticker, estimator, window_key, int(min_periods),
        _STATE_CONFIG.version(), int(_STATE_CONFIG.confirmation_days),
        tuple(sorted(FORWARD_HORIZONS.items())), sampling, start, end,
        tuple(sorted(DEFAULT_MIN_SAMPLE_GATES.items())), data_version,
    )
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    # State side: confirmed diagnostic state per date (already-lagged, as-of t).
    state_frame = _confirmed_state_frame(ordered, config_key, ticker, estimator, window_key, min_periods)

    # Optional date-range filter applies to the *signal* (decision) date only.
    if start is not None:
        state_frame = state_frame[state_frame["date"] >= pd.Timestamp(start)]
    if end is not None:
        state_frame = state_frame[state_frame["date"] <= pd.Timestamp(end)]

    # Forward side: UNLAGGED ffilled close read strictly after t.
    forward = _forward_outcome_frame(ticker, with_drawdowns=True)
    if forward.empty:
        response = SignalOutcomeResponse(
            ticker=ticker, config_key=config_key, reference_estimator=estimator,
            sampling=sampling, horizons=horizon_labels, rows=[], disclaimer=_OUTCOME_DISCLAIMER,
        )
        cache.set(key, response)
        return response

    non_overlapping = sampling == "non_overlapping"
    rows: list[SignalOutcomeRow] = []
    for label in horizon_labels:
        table = build_volatility_signal_outcome_table(
            state_frame, forward, "confirmed_state", f"forward_return_{label}",
            non_overlapping=non_overlapping, min_sample_gates=DEFAULT_MIN_SAMPLE_GATES,
        )
        for _, r in table.iterrows():
            rows.append(
                SignalOutcomeRow(
                    state=str(r["state"]),
                    horizon=label,
                    effective_observations=int(r["effective_observations"]),
                    sample_quality=str(r["sample_quality"]),
                    mean_return=_clean_float(r["mean_return"]),
                    median_return=_clean_float(r["median_return"]),
                    hit_rate=_clean_float(r["hit_rate"]),
                    std_return=_clean_float(r["std_return"]),
                    worst_return=_clean_float(r["worst_return"]),
                    best_return=_clean_float(r["best_return"]),
                    forward_max_drawdown=_clean_float(r["forward_max_drawdown"]),
                )
            )

    response = SignalOutcomeResponse(
        ticker=ticker, config_key=config_key, reference_estimator=estimator,
        sampling=sampling, horizons=horizon_labels, rows=rows, disclaimer=_OUTCOME_DISCLAIMER,
    )
    cache.set(key, response)
    return response


# The combined-condition signals are descriptive *conditions*, not the unified
# confirmed state — same honesty caveat, plus a note that a date may satisfy
# several conditions at once (they are analysed independently).
_CONDITION_DISCLAIMER = (
    "Combined-condition signals are independent point-in-time conditions on the "
    "already-lagged feature surface (a single day may satisfy several). Outcomes "
    "describe what historically followed each condition in this single sample — no "
    "causality, no guarantee. Non-overlapping sampling is the default."
)


def _confirmed_state_frame(
    ordered: pd.DataFrame,
    config_key: str,
    ticker: str,
    estimator: str,
    window_key: str,
    min_periods: int,
) -> pd.DataFrame:
    """``date`` + ``confirmed_state`` for one ticker (already-lagged, as-of ``t``).

    The shared signal side for the Phase 9 outcome / distribution endpoints: the
    persistence-debounced confirmed diagnostic state per date.
    """
    feats = _features_frame(ordered, config_key, ticker, estimator, window_key, min_periods)
    _, confirmed = compute_state_series(feats, _STATE_CONFIG)
    return pd.DataFrame(
        {"date": pd.to_datetime(feats["date"].to_numpy()), "confirmed_state": confirmed.to_numpy()}
    )


def _per_date_agreement(ordered: pd.DataFrame) -> pd.Series:
    """Per-date estimator-agreement label aligned to ``ordered`` (Phase 4 classification)."""
    dispersion = compute_estimator_dispersion(ordered, VOL_ESTIMATOR_NAMES, _AGREEMENT_CONFIG.min_estimators)
    labels = [
        classify_estimator_agreement(_clean_float(rel), _clean_float(absol), _AGREEMENT_CONFIG)
        for rel, absol in zip(
            dispersion["relative_dispersion"].to_numpy(), dispersion["absolute_spread"].to_numpy()
        )
    ]
    return pd.Series(labels, index=ordered.index)


def _tlt_agg_slice() -> tuple[pd.DataFrame, str]:
    """The single-config TLT/AGG surface slice + its freshness token (cross-asset condition).

    Returns ``(slice, data_version)``; the slice is empty and the token ``""`` when
    TLT or AGG is missing. The token lets callers (a) include the cross-asset
    surface's freshness in their cache key — so a TLT/AGG-only refresh invalidates
    a *different* ticker's cached conditions — and (b) key the percentile cache.
    """
    raw = get_volatility_features(["TLT", "AGG"])
    if raw.empty or DEFAULT_REFERENCE_ESTIMATOR not in raw.columns:
        return raw.iloc[0:0], ""
    df_slice, _ = _single_config_slice(raw)
    if not {"TLT", "AGG"} <= set(df_slice["ticker"].dropna().unique()):
        return df_slice.iloc[0:0], ""
    return df_slice, surface_data_version(df_slice)


def _tlt_agg_relative_percentile(cross_slice: pd.DataFrame, data_version: str, window_key: str, min_periods: int) -> pd.Series:
    """Date-indexed historical percentile of the TLT/AGG relative-vol ratio (cross-asset condition).

    Uses the reference estimator (rolling_20) consistently with Phase 7, regardless
    of the per-ticker estimator. Empty when the TLT/AGG slice is empty, so the
    cross-asset combined condition is simply not emitted. Cached on the TLT/AGG
    ``data_version`` so it is computed once and shared across per-ticker requests
    (Phase 7-style cross-asset key) rather than recomputed on every call.
    """
    if cross_slice.empty:
        return pd.Series(dtype=float)
    key = ("tlt_agg_rel_pct", "v1", DEFAULT_REFERENCE_ESTIMATOR, window_key, int(min_periods), data_version)
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    ratios = compute_relative_volatility_ratios(_wide_vol(cross_slice, DEFAULT_REFERENCE_ESTIMATOR), [("TLT", "AGG")])
    if "TLT/AGG" not in ratios.columns:
        pct = pd.Series(dtype=float)
    else:
        pct = compute_rolling_percentile(ratios["TLT/AGG"], _resolve_window(window_key), int(min_periods))
        pct.index = pd.to_datetime(ratios.index)
    cache.set(key, pct)
    return pct


def _combined_conditions_frame(
    ordered: pd.DataFrame,
    config_key: str,
    ticker: str,
    estimator: str,
    window_key: str,
    min_periods: int,
    cross_slice: pd.DataFrame,
    cross_data_version: str,
) -> pd.DataFrame:
    """``date`` + one boolean column per combined condition for one ticker (Phase 9).

    Enriches the per-row Phase 1–3 features with the per-date estimator agreement
    (Phase 4), the as-of-(t-1) 20-day price return (Phase 5) and — when the TLT/AGG
    ``cross_slice`` is present — the cross-asset TLT/AGG relative-vol percentile
    (Phase 7), then defers the actual condition maths to the pure
    ``compute_combined_condition_flags``. The caller supplies the cross-asset slice
    + freshness token so they also feed the endpoint's cache key.
    """
    feats = _features_frame(ordered, config_key, ticker, estimator, window_key, min_periods)
    feats["date"] = pd.to_datetime(feats["date"])
    # Per-date agreement (same row order as `ordered` -> `feats`).
    feats["estimator_agreement"] = _per_date_agreement(ordered).to_numpy()

    # As-of-(t-1) 20D price return, joined one-to-one on date.
    price_ret = _price_return_20d(get_etf_history([ticker]))
    if len(price_ret):
        pr = price_ret.rename("asset_return_20d").reset_index()
        pr.columns = ["date", "asset_return_20d"]
        pr["date"] = pd.to_datetime(pr["date"])
        feats = feats.merge(pr, on="date", how="left", validate="one_to_one")
    else:
        feats["asset_return_20d"] = float("nan")

    # Cross-asset TLT/AGG relative-vol percentile (only when both assets exist).
    rel = _tlt_agg_relative_percentile(cross_slice, cross_data_version, window_key, min_periods)
    if len(rel):
        rr = rel.rename("relative_pair_percentile").reset_index()
        rr.columns = ["date", "relative_pair_percentile"]
        rr["date"] = pd.to_datetime(rr["date"])
        feats = feats.merge(rr, on="date", how="left", validate="one_to_one")

    return compute_combined_condition_flags(feats, PRICE_DIRECTION_THRESHOLD)


def get_signal_outcome_conditions(
    ticker: str,
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    sampling: str = "non_overlapping",
    start: str | None = None,
    end: str | None = None,
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> SignalOutcomeResponse:
    """Forward outcomes for the **combined-condition** signals for one ticker (Phase 9).

    Same shape, alignment and gating as :func:`get_signal_outcomes`, but the signal
    side is the set of combined conditions (vol rising + price falling, agreement
    Low, …) rather than the unified confirmed state. ``state`` carries the condition
    label. Cached on the §7.2-style key extended with the agreement/state config
    versions and the condition parameters.
    """
    if sampling not in {"non_overlapping", "all"}:
        raise ValueError(f"unknown sampling '{sampling}' (expected 'non_overlapping' or 'all')")
    _validate_estimator(estimator)
    _resolve_window(window_key)

    ordered, config_key = _load_ticker_ordered(ticker)
    horizon_labels = list(FORWARD_HORIZONS)

    def _empty() -> SignalOutcomeResponse:
        return SignalOutcomeResponse(
            ticker=ticker, config_key=config_key, reference_estimator=estimator,
            sampling=sampling, horizons=horizon_labels, rows=[], disclaimer=_CONDITION_DISCLAIMER,
        )

    if ordered.empty or estimator not in ordered.columns:
        return _empty()

    data_version = surface_data_version(ordered)
    # The cross-asset condition depends on the TLT/AGG surface, not just this
    # ticker's — so the TLT/AGG freshness token is part of the key (a TLT/AGG-only
    # refresh must invalidate another ticker's cached conditions, §7.5).
    cross_slice, cross_data_version = _tlt_agg_slice()
    key = (
        "vol_outcome_conditions", "v1", config_key, ticker, estimator, window_key, int(min_periods),
        _STATE_CONFIG.version(), _AGREEMENT_CONFIG.version(), PRICE_DIRECTION_THRESHOLD,
        RECENT_PEAK_LOOKBACK, RELATIVE_EXTREME_PERCENTILE,
        tuple(sorted(FORWARD_HORIZONS.items())), sampling, start, end,
        tuple(sorted(DEFAULT_MIN_SAMPLE_GATES.items())), data_version, cross_data_version,
    )
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    conditions = _combined_conditions_frame(
        ordered, config_key, ticker, estimator, window_key, min_periods, cross_slice, cross_data_version
    )
    if start is not None:
        conditions = conditions[conditions["date"] >= pd.Timestamp(start)]
    if end is not None:
        conditions = conditions[conditions["date"] <= pd.Timestamp(end)]

    forward = _forward_outcome_frame(ticker, with_drawdowns=True)
    if forward.empty:
        response = _empty()
        cache.set(key, response)
        return response

    non_overlapping = sampling == "non_overlapping"
    rows: list[SignalOutcomeRow] = []
    for label in horizon_labels:
        table = build_combined_condition_outcome_table(
            conditions, forward, f"forward_return_{label}",
            non_overlapping=non_overlapping, min_sample_gates=DEFAULT_MIN_SAMPLE_GATES,
        )
        for _, r in table.iterrows():
            rows.append(
                SignalOutcomeRow(
                    state=str(r["state"]),
                    horizon=label,
                    effective_observations=int(r["effective_observations"]),
                    sample_quality=str(r["sample_quality"]),
                    mean_return=_clean_float(r.get("mean_return")),
                    median_return=_clean_float(r.get("median_return")),
                    hit_rate=_clean_float(r.get("hit_rate")),
                    std_return=_clean_float(r.get("std_return")),
                    worst_return=_clean_float(r.get("worst_return")),
                    best_return=_clean_float(r.get("best_return")),
                    forward_max_drawdown=_clean_float(r.get("forward_max_drawdown")),
                )
            )

    response = SignalOutcomeResponse(
        ticker=ticker, config_key=config_key, reference_estimator=estimator,
        sampling=sampling, horizons=horizon_labels, rows=rows, disclaimer=_CONDITION_DISCLAIMER,
    )
    cache.set(key, response)
    return response


def get_signal_outcome_distribution(
    ticker: str,
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    horizon: str = "1M",
    sampling: str = "non_overlapping",
    start: str | None = None,
    end: str | None = None,
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> SignalOutcomeDistributionResponse:
    """Per-state forward-return *samples* at one ``horizon`` for the box plot (Phase 9).

    The companion to :func:`get_signal_outcomes`: identical state side (already-lagged
    confirmed state), identical unlagged after-``t`` forward side and identical
    sampling, but it returns the raw per-observation forward returns per diagnostic
    state so the frontend can draw a box per state. Cached on the outcome key plus
    the single horizon.
    """
    if horizon not in FORWARD_HORIZONS:
        raise ValueError(f"unknown horizon '{horizon}' (expected one of {sorted(FORWARD_HORIZONS)})")
    if sampling not in {"non_overlapping", "all"}:
        raise ValueError(f"unknown sampling '{sampling}' (expected 'non_overlapping' or 'all')")
    _validate_estimator(estimator)
    _resolve_window(window_key)

    ordered, config_key = _load_ticker_ordered(ticker)

    def _empty() -> SignalOutcomeDistributionResponse:
        return SignalOutcomeDistributionResponse(
            ticker=ticker, config_key=config_key, reference_estimator=estimator,
            sampling=sampling, horizon=horizon, distributions=[], disclaimer=_OUTCOME_DISCLAIMER,
        )

    if ordered.empty or estimator not in ordered.columns:
        return _empty()

    data_version = surface_data_version(ordered)
    key = (
        "vol_outcome_dist", "v1", config_key, ticker, estimator, window_key, int(min_periods),
        _STATE_CONFIG.version(), int(_STATE_CONFIG.confirmation_days),
        horizon, sampling, start, end, data_version,
    )
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    state_frame = _confirmed_state_frame(ordered, config_key, ticker, estimator, window_key, min_periods)
    if start is not None:
        state_frame = state_frame[state_frame["date"] >= pd.Timestamp(start)]
    if end is not None:
        state_frame = state_frame[state_frame["date"] <= pd.Timestamp(end)]

    forward_returns = _forward_outcome_frame(ticker, with_drawdowns=False)
    if forward_returns.empty:
        response = _empty()
        cache.set(key, response)
        return response

    samples = build_state_return_distribution(
        state_frame, forward_returns, "confirmed_state", f"forward_return_{horizon}",
        non_overlapping=(sampling == "non_overlapping"), states=OUTCOME_STATES,
    )
    distributions = [
        StateReturnDistribution(state=state, effective_observations=len(returns), returns=returns)
        for state, returns in samples.items()
        if returns  # a box needs at least one realised forward return
    ]

    response = SignalOutcomeDistributionResponse(
        ticker=ticker, config_key=config_key, reference_estimator=estimator,
        sampling=sampling, horizon=horizon, distributions=distributions, disclaimer=_OUTCOME_DISCLAIMER,
    )
    cache.set(key, response)
    return response


# --------------------------------------------------------------------------- #
# Phase 10 — passive strategy-integration snapshot interface
# --------------------------------------------------------------------------- #


def _snapshot_provider(
    estimator: str, window_key: str, min_periods: int
) -> tuple[VolatilitySignalSnapshotProvider | None, str, pd.Timestamp | None]:
    """Build a snapshot provider over the persisted surface (+ ETF prices).

    Returns ``(provider, config_key, latest_date)``; provider is ``None`` when the
    surface is empty. The provider wraps a single-``config_key`` ``VolatilityFeatureSurface``
    and the matching ETF close history, sharing the process-wide state/agreement
    configs so versions line up with the rest of the dashboard.
    """
    raw = get_volatility_features()
    if raw.empty:
        return None, "", None
    df_slice, config_key = _single_config_slice(raw)
    tickers = sorted(str(t) for t in df_slice["ticker"].dropna().unique())
    surface = VolatilityFeatureSurface(
        values=df_slice.reset_index(drop=True), config=VolatilityFeatureConfig(), tickers=tickers
    )
    latest = df_slice["date"].max() if not df_slice.empty else None
    provider = VolatilitySignalSnapshotProvider(
        surface=surface,
        prices=get_etf_history(tickers),
        reference_estimator=estimator,
        historical_window=window_key,
        minimum_history=int(min_periods),
        state_config=_STATE_CONFIG,
        agreement_config=_AGREEMENT_CONFIG,
        stability_window=window_key,
    )
    return provider, config_key, latest


def _asset_snapshot_to_response(snap) -> AssetVolatilitySnapshotResponse:
    """Map the pure ``AssetVolatilitySignalSnapshot`` dataclass to its API model."""
    return AssetVolatilitySnapshotResponse(
        ticker=snap.ticker,
        as_of_date=_iso_date(snap.as_of_date),
        information_through_date=_iso_date(snap.information_through_date),
        config_key=snap.config_key,
        reference_estimator=snap.reference_estimator,
        historical_window=snap.historical_window,
        minimum_history=snap.minimum_history,
        state_config_version=snap.state_config_version,
        confirmation_days=snap.confirmation_days,
        agreement_config_version=snap.agreement_config_version,
        stability_window=snap.stability_window,
        annualized_volatility=_clean_float(snap.annualized_volatility),
        historical_percentile=_clean_float(snap.historical_percentile),
        percentile_ordinal=percentile_to_ordinal(_clean_float(snap.historical_percentile)),
        volatility_level=snap.volatility_level,
        change_5d=_clean_float(snap.change_5d),
        change_20d=_clean_float(snap.change_20d),
        direction=snap.direction,
        short_long_ratio=_clean_float(snap.short_long_ratio),
        term_state=snap.term_state,
        instantaneous_state=snap.instantaneous_state,
        confirmed_state=snap.confirmed_state,
        estimator_agreement=snap.estimator_agreement,
        absolute_spread=_clean_float(snap.absolute_spread),
        relative_dispersion=_clean_float(snap.relative_dispersion),
        asset_return_20d=_clean_float(snap.asset_return_20d),
        price_volatility_context=snap.price_volatility_context,
        stability_percentile=_clean_float(snap.stability_percentile),
        estimate_stability=snap.estimate_stability,
        raw_vol_of_vol=_clean_float(snap.raw_vol_of_vol),
    )


def _resolve_as_of(as_of: str | None, latest: pd.Timestamp | None) -> pd.Timestamp | None:
    """Parse an ISO ``as_of`` (or default to the surface's latest date)."""
    if as_of:
        return pd.Timestamp(as_of)
    return latest


def get_asset_signal_snapshot(
    ticker: str,
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    as_of: str | None = None,
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> AssetVolatilitySnapshotResponse:
    """Passive point-in-time signal snapshot for one ticker (Phase 10).

    Retrieves via the single existing ``get_ticker_snapshot`` as-of path and packages
    the Phase 1–8 diagnostics + reproducibility metadata. Defaults to the latest
    surface date. Cached on the §7.2-style key + the as-of date.
    """
    _validate_estimator(estimator)
    _resolve_window(window_key)

    provider, config_key, latest = _snapshot_provider(estimator, window_key, min_periods)
    if provider is None or latest is None:
        # Empty surface: a metadata-only blank snapshot (no row to read).
        blank = VolatilitySignalSnapshotProvider(
            surface=VolatilityFeatureSurface(values=pd.DataFrame(), config=VolatilityFeatureConfig(), tickers=[]),
            reference_estimator=estimator, historical_window=window_key,
            minimum_history=int(min_periods), state_config=_STATE_CONFIG,
            agreement_config=_AGREEMENT_CONFIG, stability_window=window_key,
        )
        as_of_blank = pd.Timestamp(as_of) if as_of else pd.Timestamp.now().normalize()
        return _asset_snapshot_to_response(blank._missing_snapshot(ticker, as_of_blank))

    as_of_ts = _resolve_as_of(as_of, latest)
    data_version = surface_data_version(provider.surface.values)
    key = (
        "vol_snapshot", "v1", config_key, ticker, estimator, window_key, int(min_periods),
        _STATE_CONFIG.version(), int(_STATE_CONFIG.confirmation_days), _AGREEMENT_CONFIG.version(),
        str(as_of_ts.date()) if as_of_ts is not None else None, data_version,
    )
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    snap = provider.get_volatility_signal_snapshot(ticker, as_of_ts)
    response = _asset_snapshot_to_response(snap)
    cache.set(key, response)
    return response


def get_cross_asset_signal_snapshot(
    estimator: str = DEFAULT_REFERENCE_ESTIMATOR,
    window_key: str = DEFAULT_HISTORICAL_WINDOW,
    as_of: str | None = None,
    min_periods: int = MIN_PERCENTILE_HISTORY,
) -> CrossAssetVolatilitySnapshotResponse:
    """Passive all-asset snapshot: per-asset snapshots + ratios + risk ranking (Phase 10)."""
    _validate_estimator(estimator)
    _resolve_window(window_key)

    provider, config_key, latest = _snapshot_provider(estimator, window_key, min_periods)
    if provider is None or latest is None:
        return CrossAssetVolatilitySnapshotResponse(
            as_of_date=None, information_through_date=None, config_key="",
            reference_estimator=estimator, historical_window=window_key,
            minimum_history=int(min_periods), state_config_version=_STATE_CONFIG.version(),
            confirmation_days=int(_STATE_CONFIG.confirmation_days),
            agreement_config_version=_AGREEMENT_CONFIG.version(), stability_window=window_key,
            assets=[], ratios=[], ranking=[],
        )

    as_of_ts = _resolve_as_of(as_of, latest)
    data_version = surface_data_version(provider.surface.values)
    key = (
        "vol_snapshot_cross", "v1", config_key, estimator, window_key, int(min_periods),
        _STATE_CONFIG.version(), int(_STATE_CONFIG.confirmation_days), _AGREEMENT_CONFIG.version(),
        str(as_of_ts.date()) if as_of_ts is not None else None, data_version,
    )
    cache = _pct_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    snap = provider.get_cross_asset_volatility_snapshot(as_of_ts)
    response = CrossAssetVolatilitySnapshotResponse(
        as_of_date=_iso_date(snap.as_of_date),
        information_through_date=_iso_date(snap.information_through_date),
        config_key=snap.config_key,
        reference_estimator=snap.reference_estimator,
        historical_window=snap.historical_window,
        minimum_history=snap.minimum_history,
        state_config_version=snap.state_config_version,
        confirmation_days=snap.confirmation_days,
        agreement_config_version=snap.agreement_config_version,
        stability_window=snap.stability_window,
        assets=[_asset_snapshot_to_response(a) for a in snap.assets],
        ratios=[
            CrossAssetRatioSnapshotRow(
                pair=r.pair, current_ratio=_clean_float(r.current_ratio),
                percentile_ordinal=_clean_ordinal(r.percentile_ordinal),
                relative_risk_state=r.relative_risk_state,
            )
            for r in snap.ratios
        ],
        ranking=[
            AssetRiskRankSnapshotRow(
                rank=r.rank, ticker=r.ticker,
                annualized_volatility=_clean_float(r.annualized_volatility),
                historical_percentile=_clean_float(r.historical_percentile),
                confirmed_state=r.confirmed_state,
            )
            for r in snap.ranking
        ],
    )
    cache.set(key, response)
    return response
