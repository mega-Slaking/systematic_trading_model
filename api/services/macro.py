"""Macro service (spec endpoints 10 + 11).

Wraps ``db_reader.get_macro_history``. Each indicator series is NaN-dropped onto
its own date axis (macro is monthly/sparse, §2.6); the yield-curve endpoint
computes the 10Y-2Y spread the page currently derives inline.

Endpoint 10 serves both the **raw** ``macro_data`` columns and the **derived**
features computed at request time by ``src/signals_macro/macro_features.py``
(``docs/macro_data_interpretability.md`` Phase 1, decision #2: derive, don't
persist). Every series carries a ``meta`` describing its true source/units so the
client can label and format it honestly — this is where the legacy
``cpi``→"CPI YoY" and ``pmi``→"PMI" mislabels (§3.2) are corrected at the source.

``meta.unit`` vocabulary (the React layer formats off this):
  * ``level``    — a plain index/count (CPI index, payrolls, CFNAI, sentiment).
  * ``pct``      — a value already in percent (yields, fed funds, unemployment).
  * ``pct_frac`` — a decimal fraction to render as a percent (CPI YoY = 0.031 → 3.1%).
  * ``pp``       — a percentage-point change (yield/spread/real-rate changes; the
                   client may × 100 to basis points for yield deltas).
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

import pandas as pd

from src.signals_macro.macro_features import (
    CURVE_REGIMES,
    MACRO_REGIMES,
    MACRO_REGIME_PRIORS,
    build_conditional_forward_return_table,
    compute_curve_regime,
    compute_forward_returns,
    compute_macro_regime,
    derive_macro_features,
    inversion_intervals,
    macro_availability_dates,
)
from src.storage.db_reader import get_backtest_regime_trace, get_etf_history, get_macro_history
from src.universe import UNIVERSE

from api.schemas.common import CategoricalSeries
from api.schemas.macro import (
    ConditionalReturnsResponse,
    ForwardReturnScatterResponse,
    MacroResponse,
    MacroSnapshotCard,
    MacroSnapshotResponse,
    RegimeTimelineResponse,
    ScatterPoint,
    YieldCurveResponse,
)
from api.serialization.frames import df_to_categorical_series, df_to_series, df_to_table, to_iso

# Raw indicators from get_macro_history (the FE picks a subset per chart).
_MACRO_INDICATORS: tuple[str, ...] = (
    "cpi",
    "core_cpi",
    "pmi",
    "gs2",
    "gs10",
    "unemployment",
    "payrolls",
    "fed_funds",
    "consumer_sentiment",
    "hy_oas",
    "jobless_claims",
)

# Derived feature columns surfaced from macro_features (passthrough levels that
# duplicate a raw column — gs2/gs10/fed_funds/unemployment — are intentionally
# excluded; the raw keys above already carry them).
_DERIVED_INDICATORS: tuple[str, ...] = (
    "cpi_yoy",
    "cpi_yoy_change_3m",
    "cpi_yoy_acceleration",
    "core_cpi_yoy",
    "activity_change_3m",
    "unemployment_change_3m",
    "unemployment_change_6m",
    "unemployment_minus_12m_low",
    "fed_funds_change_3m",
    "real_policy_rate",
    "curve_spread",
    "yield_2y_change_1m",
    "yield_2y_change_3m",
    "yield_10y_change_1m",
    "yield_10y_change_3m",
    "curve_spread_change_3m",
)

# Per-indicator metadata (label/source/units/frequency/neutral/note). Keys absent
# here fall back to ``None`` meta. Sources per src/api_fetch/fetch_macro_data.py.
_INDICATOR_META: dict[str, dict] = {
    # --- raw levels (note the honest source labels that fix the legacy mislabels) ---
    "cpi": {"label": "CPI Index", "unit": "level", "source": "CPIAUCSL", "frequency": "monthly",
            "note": "Index level — NOT year-over-year inflation. Use cpi_yoy for inflation."},
    "core_cpi": {"label": "Core CPI Index", "unit": "level", "source": "CPILFESL", "frequency": "monthly",
                 "note": "Index level, ex food & energy."},
    "pmi": {"label": "CFNAI (Chicago Fed National Activity Index)", "unit": "level", "source": "CFNAI",
            "frequency": "monthly", "neutral": 0,
            "note": "Activity index centred on 0 (not a 50-neutral PMI); legacy 'PMI' label was wrong."},
    "gs2": {"label": "2Y Treasury Yield", "unit": "pct", "source": "GS2", "frequency": "monthly"},
    "gs10": {"label": "10Y Treasury Yield", "unit": "pct", "source": "GS10", "frequency": "monthly"},
    "unemployment": {"label": "Unemployment Rate", "unit": "pct", "source": "UNRATE", "frequency": "monthly"},
    "payrolls": {"label": "Nonfarm Payrolls", "unit": "level", "source": "PAYEMS", "frequency": "monthly"},
    "fed_funds": {"label": "Fed Funds Rate", "unit": "pct", "source": "FEDFUNDS", "frequency": "monthly"},
    "consumer_sentiment": {"label": "Consumer Sentiment", "unit": "level", "source": "UMCSENT", "frequency": "monthly"},
    "hy_oas": {"label": "Baa–10Y Credit Spread", "unit": "pct", "source": "BAA10Y", "frequency": "monthly",
               "note": "Baa-corporate minus 10Y Treasury spread proxy (not a true HY OAS)."},
    "jobless_claims": {"label": "Initial Jobless Claims", "unit": "level", "source": "ICSA", "frequency": "monthly"},
    # --- derived (decimal-fraction YoY family) ---
    "cpi_yoy": {"label": "CPI YoY", "unit": "pct_frac", "source": "CPIAUCSL", "frequency": "monthly",
                "note": "Year-over-year inflation as a decimal fraction (× 100 for %)."},
    "cpi_yoy_change_3m": {"label": "Δ CPI YoY (3m)", "unit": "pct_frac", "source": "CPIAUCSL", "frequency": "monthly"},
    "cpi_yoy_acceleration": {"label": "CPI YoY acceleration", "unit": "pct_frac", "source": "CPIAUCSL", "frequency": "monthly"},
    "core_cpi_yoy": {"label": "Core CPI YoY", "unit": "pct_frac", "source": "CPILFESL", "frequency": "monthly"},
    # --- derived (changes / levels in percentage points) ---
    "activity_change_3m": {"label": "Δ CFNAI (3m)", "unit": "level", "source": "CFNAI", "frequency": "monthly"},
    "unemployment_change_3m": {"label": "Δ Unemployment (3m)", "unit": "pp", "source": "UNRATE", "frequency": "monthly"},
    "unemployment_change_6m": {"label": "Δ Unemployment (6m)", "unit": "pp", "source": "UNRATE", "frequency": "monthly"},
    "unemployment_minus_12m_low": {"label": "Unemployment vs 12m low", "unit": "pp", "source": "UNRATE",
                                   "frequency": "monthly", "note": "Level minus trailing-12m minimum (Sahm-style)."},
    "fed_funds_change_3m": {"label": "Δ Fed Funds (3m)", "unit": "pp", "source": "FEDFUNDS", "frequency": "monthly"},
    "real_policy_rate": {"label": "Real Policy Rate", "unit": "pp", "source": "FEDFUNDS,CPILFESL", "frequency": "monthly",
                         "note": "fed_funds − core CPI YoY (pp); positive = restrictive."},
    "curve_spread": {"label": "10Y–2Y Spread", "unit": "pp", "source": "GS10,GS2", "frequency": "monthly"},
    "yield_2y_change_1m": {"label": "Δ 2Y Yield (1m)", "unit": "pp", "source": "GS2", "frequency": "monthly"},
    "yield_2y_change_3m": {"label": "Δ 2Y Yield (3m)", "unit": "pp", "source": "GS2", "frequency": "monthly"},
    "yield_10y_change_1m": {"label": "Δ 10Y Yield (1m)", "unit": "pp", "source": "GS10", "frequency": "monthly"},
    "yield_10y_change_3m": {"label": "Δ 10Y Yield (3m)", "unit": "pp", "source": "GS10", "frequency": "monthly"},
    "curve_spread_change_3m": {"label": "Δ 10Y–2Y Spread (3m)", "unit": "pp", "source": "GS10,GS2", "frequency": "monthly"},
}

# All indicator keys endpoint 10 can serve (raw + derived), in a stable order.
_ALL_INDICATORS: tuple[str, ...] = _MACRO_INDICATORS + _DERIVED_INDICATORS


def _macro_frame() -> pd.DataFrame:
    """Raw ``macro_data`` joined with the derived features (one row per month).

    Both sides are date-keyed and the derived subset excludes raw column names, so
    the left-join on ``date`` introduces no column clashes.
    """
    raw = get_macro_history().sort_values("date").reset_index(drop=True)
    derived = derive_macro_features(raw)
    derived_subset = derived[["date", *_DERIVED_INDICATORS]]
    return raw.merge(derived_subset, on="date", how="left")


def get_macro(indicators: list[str] | None = None) -> MacroResponse:
    """One series per requested indicator (all by default), each NaN-dropped.

    Serves raw and derived indicators alike; each series carries its
    source/units ``meta`` (see module docstring).
    """
    df = _macro_frame()
    wanted = [i for i in (indicators or _ALL_INDICATORS) if i in df.columns]

    series = []
    for indicator in wanted:
        sub = df[["date", indicator]].dropna(subset=[indicator])
        if sub.empty:
            continue
        series.append(df_to_series(sub, name=indicator, x="date", y=indicator, meta=_INDICATOR_META.get(indicator)))
    return MacroResponse(series=series)


def get_yield_curve() -> YieldCurveResponse:
    """10Y/2Y yields, the 10Y-2Y spread, and curve-regime interpretation (Phase 2)."""
    df = get_macro_history().sort_values("date").reset_index(drop=True)
    yields = df.dropna(subset=["gs10", "gs2"]).copy()
    yields["spread"] = yields["gs10"] - yields["gs2"]

    # Curve regime over a 3-month lookback + inverted spans (both derived from the
    # single-source feature layer; categorical regime uses the §12 #5 wire format).
    yields = yields.join(compute_curve_regime(yields["gs2"], yields["gs10"], lookback=3))
    intervals = inversion_intervals(yields["date"], yields["spread"])
    current_regime = next(
        (label for label in reversed(yields["curve_regime"].tolist()) if isinstance(label, str)),
        None,
    )

    return YieldCurveResponse(
        gs10=df_to_series(yields, name="10Y Yield", x="date", y="gs10"),
        gs2=df_to_series(yields, name="2Y Yield", x="date", y="gs2"),
        spread=df_to_series(yields, name="10Y-2Y Spread", x="date", y="spread", meta={"fill": "tozeroy"}),
        curve_regime=df_to_categorical_series(
            yields,
            name="Curve Regime",
            value_col="curve_regime_code",
            label_col="curve_regime",
            categories=CURVE_REGIMES,
        ),
        inverted_intervals=intervals,
        current_regime=current_regime,
    )


# A monthly series more than this many days behind the newest macro date is
# flagged stale (allows for normal ~1-month publication lags).
_SNAPSHOT_STALE_DAYS = 75

# (key, label, value column, 3-month-change column, unit) for the numeric cards.
_SNAPSHOT_CARDS: tuple[tuple[str, str, str, str, str], ...] = (
    ("cpi_yoy", "CPI YoY", "cpi_yoy", "cpi_yoy_change_3m", "pct_frac"),
    ("cfnai", "CFNAI", "pmi", "activity_change_3m", "level"),
    ("unemployment", "Unemployment", "unemployment", "unemployment_change_3m", "pct"),
    ("fed_funds", "Fed Funds", "fed_funds", "fed_funds_change_3m", "pct"),
    ("real_policy_rate", "Policy Rate", "real_policy_rate", "real_policy_rate_change_3m", "pp"),
    ("gs2", "2Y Yield", "gs2", "yield_2y_change_3m", "pct"),
    ("gs10", "10Y Yield", "gs10", "yield_10y_change_3m", "pct"),
    ("curve_spread", "10Y-2Y Spread", "curve_spread", "curve_spread_change_3m", "pp"),
)


def _numeric_card(
    df: pd.DataFrame, *, key: str, label: str, value_col: str, change_col: str, unit: str, newest, stale_days: int
) -> MacroSnapshotCard | None:
    """Build a numeric snapshot card from the latest non-null value of ``value_col``."""
    sub = df[["date", value_col, change_col]].dropna(subset=[value_col])
    if sub.empty:
        return None
    last = sub.iloc[-1]
    change = None if pd.isna(last[change_col]) else float(last[change_col])
    direction = None if change is None else ("up" if change > 0 else "down" if change < 0 else "flat")
    return MacroSnapshotCard(
        key=key,
        label=label,
        value=float(last[value_col]),
        unit=unit,
        observation_date=to_iso(pd.Series([last["date"]])).iloc[0],
        change_3m=change,
        direction=direction,
        is_stale=bool((newest - last["date"]).days > stale_days),
    )


def _categorical_card(
    df: pd.DataFrame, *, key: str, label: str, col: str, newest, stale_days: int
) -> MacroSnapshotCard | None:
    """Build a categorical card (string value, no unit/change) from a label column."""
    rows = df[["date", col]].dropna(subset=[col])
    if rows.empty:
        return None
    last = rows.iloc[-1]
    return MacroSnapshotCard(
        key=key, label=label, value=str(last[col]), unit=None,
        observation_date=to_iso(pd.Series([last["date"]])).iloc[0],
        change_3m=None, direction=None,
        is_stale=bool((newest - last["date"]).days > stale_days),
    )


def get_macro_snapshot() -> MacroSnapshotResponse:
    """Latest-reading cards for the macro dashboard's snapshot row (Phases 3 + 4).

    Each numeric card reports its indicator's latest value, that value's own
    observation date, its 3-month change/direction, and a stale flag; two
    categorical cards report the current macro regime and curve regime.
    """
    df = _macro_frame()
    df["date"] = pd.to_datetime(df["date"])
    df["real_policy_rate_change_3m"] = df["real_policy_rate"].diff(3)
    df["curve_regime"] = compute_curve_regime(df["gs2"], df["gs10"], lookback=3)["curve_regime"].to_numpy()
    # `activity_level` is the CFNAI level (raw `pmi`), the regime classifier's input name.
    df["activity_level"] = df["pmi"]
    df["macro_regime"] = compute_macro_regime(df)["macro_regime"].to_numpy()
    newest = df["date"].max()

    cards: list[MacroSnapshotCard] = []
    for key, label, value_col, change_col, unit in _SNAPSHOT_CARDS:
        card = _numeric_card(
            df, key=key, label=label, value_col=value_col, change_col=change_col,
            unit=unit, newest=newest, stale_days=_SNAPSHOT_STALE_DAYS,
        )
        if card is not None:
            cards.append(card)

    for key, label, col in (("macro_regime", "Macro Regime", "macro_regime"), ("curve_regime", "Curve Regime", "curve_regime")):
        card = _categorical_card(df, key=key, label=label, col=col, newest=newest, stale_days=_SNAPSHOT_STALE_DAYS)
        if card is not None:
            cards.append(card)

    return MacroSnapshotResponse(cards=cards, as_of=to_iso(pd.Series([newest])).iloc[0])


# Engine's binary duration-support signal, mapped for the comparison overlay.
_ENGINE_DURATION_CATEGORIES: dict[int, str] = {0: "No duration support", 1: "Supports duration"}


def _engine_regime_overlay() -> CategoricalSeries | None:
    """The engine's ``macro_supports_duration`` over time (decision #6 comparison).

    Returns ``None`` if no backtest regime trace exists yet. The regime columns are
    macro-driven (scenario-independent), so we dedupe to one row per date.
    """
    try:
        trace = get_backtest_regime_trace()
    except Exception:
        return None
    if trace.empty or "macro_supports_duration" not in trace.columns:
        return None
    trace = (
        trace.dropna(subset=["macro_supports_duration"])
        .drop_duplicates("date")
        .sort_values("date")
    )
    if trace.empty:
        return None
    codes = trace["macro_supports_duration"].astype(bool).astype(int).astype(float)
    overlay = pd.DataFrame(
        {
            "date": trace["date"].to_numpy(),
            "code": codes.to_numpy(),
            "label": codes.map({0.0: _ENGINE_DURATION_CATEGORIES[0], 1.0: _ENGINE_DURATION_CATEGORIES[1]}).to_numpy(),
        }
    )
    return df_to_categorical_series(
        overlay, name="Engine: macro supports duration",
        value_col="code", label_col="label", categories=_ENGINE_DURATION_CATEGORIES,
    )


def get_regime_timeline() -> RegimeTimelineResponse:
    """Dashboard macro-regime timeline (+ optional engine comparison overlay)."""
    df = get_macro_history().sort_values("date").reset_index(drop=True)
    features = derive_macro_features(df)
    regime = compute_macro_regime(features)
    timeline = pd.DataFrame(
        {
            "date": features["date"].to_numpy(),
            "macro_regime_code": regime["macro_regime_code"].to_numpy(),
            "macro_regime": regime["macro_regime"].to_numpy(),
        }
    )
    dashboard = df_to_categorical_series(
        timeline, name="Macro Regime",
        value_col="macro_regime_code", label_col="macro_regime", categories=MACRO_REGIMES,
    )
    legend = {label: MACRO_REGIME_PRIORS[label] for label in MACRO_REGIMES.values()}
    return RegimeTimelineResponse(regime=dashboard, engine_regime=_engine_regime_overlay(), legend=legend)


# Forward-return horizons in trading days (~21 per month).
_FWD_HORIZONS: dict[str, int] = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}
_DEFAULT_MIN_OBSERVATIONS = 12
_CONDITIONAL_COLUMNS = [
    "regime", "etf", "n",
    "next_1m_mean", "next_3m_mean", "next_6m_mean", "next_12m_mean",
    "hit_rate_3m", "median_3m", "thin",
]


def get_conditional_returns(
    etf: str | None = None, min_observations: int = _DEFAULT_MIN_OBSERVATIONS
) -> ConditionalReturnsResponse:
    """Forward-return statistics for each ETF conditioned on the macro regime.

    The macro regime is lagged to an availability proxy, then forward returns are
    measured strictly *after* that date (``merge_asof`` to the first trading day
    on/after availability) — so no future macro and no future price leak into the
    conditioning row.
    """
    derived = derive_macro_features(get_macro_history())
    regime = compute_macro_regime(derived)
    cond = (
        pd.DataFrame(
            {
                "regime": regime["macro_regime"].to_numpy(),
                "avail_date": macro_availability_dates(derived["date"]).to_numpy(),
            }
        )
        .dropna(subset=["regime"])
        .sort_values("avail_date")
        .reset_index(drop=True)
    )

    tickers = [etf] if (etf and etf in UNIVERSE) else list(UNIVERSE)
    prices_all = get_etf_history(tickers)

    records: list[dict] = []
    for ticker in tickers:
        prices = prices_all[prices_all["ticker"] == ticker].dropna(subset=["close"]).sort_values("date")
        if prices.empty:
            continue
        fwd = compute_forward_returns(prices.set_index("date")["close"], _FWD_HORIZONS).reset_index()
        merged = pd.merge_asof(
            cond, fwd.sort_values("date"), left_on="avail_date", right_on="date", direction="forward"
        )
        table = build_conditional_forward_return_table(merged, "regime", list(_FWD_HORIZONS))
        for _, r in table.iterrows():
            n = int(r["n"])
            records.append(
                {
                    "regime": r["regime"],
                    "etf": ticker,
                    "n": n,
                    "next_1m_mean": r["1m_mean"],
                    "next_3m_mean": r["3m_mean"],
                    "next_6m_mean": r["6m_mean"],
                    "next_12m_mean": r["12m_mean"],
                    "hit_rate_3m": r["3m_hit"],
                    "median_3m": r["3m_median"],
                    "thin": bool(n < min_observations or int(r["3m_count"]) < min_observations),
                }
            )

    frame = pd.DataFrame(records, columns=_CONDITIONAL_COLUMNS)
    notes = [
        "Descriptive, not predictive: historical averages of what followed similar conditions, not forecasts.",
        "Overlapping horizons: monthly sampling makes multi-month forward returns overlap and NOT independent — treat counts as weak evidence.",
        "Macro is lagged to a reference-month-end + 1 month availability proxy to avoid look-ahead; true point-in-time release dates are unavailable.",
        f"Rows flagged 'thin' have fewer than {min_observations} observations.",
    ]
    return ConditionalReturnsResponse(
        table=df_to_table(frame),
        is_lagged=True,
        point_in_time_release_available=False,
        notes=notes,
    )


def get_forward_return_scatter(etf: str, indicator: str, horizon: str) -> ForwardReturnScatterResponse:
    """(macro reading, subsequent ETF return) pairs for the explorer scatter mode.

    Raises ``ValueError`` for an unknown ETF / horizon / indicator (the router maps
    these to 422). Forward returns are measured strictly after the reading's
    availability date (no look-ahead), so each point is honest about timing.
    """
    if etf not in UNIVERSE:
        raise ValueError(f"Unknown ETF '{etf}'. Expected one of {list(UNIVERSE)}.")
    if horizon not in _FWD_HORIZONS:
        raise ValueError(f"Unknown horizon '{horizon}'. Expected one of {list(_FWD_HORIZONS)}.")

    frame = _macro_frame()
    if indicator not in frame.columns:
        raise ValueError(f"Unknown indicator '{indicator}'.")
    frame["date"] = pd.to_datetime(frame["date"])

    cond = (
        pd.DataFrame(
            {
                "ref_date": frame["date"],
                "x": frame[indicator],
                "avail_date": macro_availability_dates(frame["date"]),
            }
        )
        .dropna(subset=["x"])
        .sort_values("avail_date")
        .reset_index(drop=True)
    )

    prices = get_etf_history([etf]).dropna(subset=["close"]).sort_values("date")
    fwd = compute_forward_returns(prices.set_index("date")["close"], {horizon: _FWD_HORIZONS[horizon]}).reset_index()
    merged = pd.merge_asof(
        cond, fwd.sort_values("date"), left_on="avail_date", right_on="date", direction="forward"
    ).dropna(subset=["x", horizon])

    points = [
        ScatterPoint(date=d, x=float(x), y=float(y))
        for d, x, y in zip(to_iso(merged["ref_date"]).tolist(), merged["x"].tolist(), merged[horizon].tolist())
    ]
    meta = _INDICATOR_META.get(indicator, {})
    return ForwardReturnScatterResponse(
        points=points,
        etf=etf,
        horizon=horizon,
        x_key=indicator,
        x_label=meta.get("label", indicator),
        x_unit=meta.get("unit"),
        n=len(points),
        note=(
            "Each point is one month: the macro reading vs the ETF's subsequent return. "
            "Association is not causation, and overlapping windows make the points non-independent."
        ),
    )
