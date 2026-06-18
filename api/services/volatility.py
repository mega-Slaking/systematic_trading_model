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
from src.volatility.direction import (
    VOL_DIRECTION_THRESHOLDS,
    VOL_RATIO_BANDS,
    change_reference_lines,
    classify_volatility_direction,
    classify_volatility_term_state,
    compute_volatility_direction_features,
    compute_volatility_term_ratio,
    ratio_reference_lines,
)
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
    EstimatorAgreementResponse,
    EstimatorComparisonRow,
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


def _features_frame(
    ordered: pd.DataFrame,
    config_key: str,
    ticker: str,
    estimator: str,
    window_key: str,
    min_periods: int,
) -> pd.DataFrame:
    """Per-row point-in-time features for one ticker — the inputs every Phase 1–3
    response is assembled from. The percentile is cached (§7.1); direction, term
    ratio, level and ordinal are vectorised/cheap and use the default state config
    so all three phases agree on a single source of thresholds.
    """
    cfg = _STATE_CONFIG
    percentile = _percentile_series_cached(ordered, config_key, ticker, estimator, window_key, min_periods)
    changes = compute_volatility_direction_features(ordered[estimator])
    ratio = _term_ratio_series(ordered)

    pct_vals = percentile.to_numpy()
    ratio_vals = ratio.to_numpy()
    change_20 = changes["change_20d"].to_numpy()

    return pd.DataFrame(
        {
            "date": ordered["date"].to_numpy(),
            "ticker": ticker,
            "current_volatility": ordered[estimator].to_numpy(),
            "percentile": pct_vals,
            "percentile_ordinal": [percentile_to_ordinal(p) for p in pct_vals],
            "volatility_level": [classify_volatility_level(p, cfg.level_thresholds()) for p in pct_vals],
            "change_5d": changes["change_5d"].to_numpy(),
            "change_20d": change_20,
            "term_ratio": ratio_vals,
            "term_state": [
                classify_volatility_term_state(r, cfg.expansion_ratio, cfg.contraction_ratio)
                for r in ratio_vals
            ],
            "direction": [
                classify_volatility_direction(c, cfg.rising_change, cfg.falling_change)
                for c in change_20
            ],
        }
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

    rows = []
    for _, r in table.iterrows():
        ticker = str(r["ticker"])
        asset_return_20d = price_ret.get(ticker)
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

_CHART_VIEWS = {"volatility", "percentile", "ratio", "change", "dispersion"}
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
