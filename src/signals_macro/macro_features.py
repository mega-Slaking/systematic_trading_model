"""Pure macro-feature derivations for the ETFs-vs-Macro dashboard.

This is the analytics-side compute layer described in
`docs/macro_data_interpretability.md` (Phase 1). It derives the interpretable
macro features the dashboard needs — YoY inflation, momentum/change features,
the real policy rate, and yield-curve change features — from the *raw* monthly
`macro_data` columns, because the DB stores only raw levels and the derived
fields the ingestion computes are dropped on insert (spec §3.2 #4).

Design rules (spec §12, resolved decisions, as refactored by "D"):
  * **Pure**: pandas only — no DB, HTTP, or `macro_signal_engine` import (so there
    is no import cycle; the dependency points *into* this module). It is
    unit-testable in isolation.
  * **Single source of truth** (refactor D): this module owns the base macro
    derivations (YoY inflation, the 10Y-2Y spread, the real policy rate, …).
    `macro_signal_engine.py` and the macro ingestion (`fetch_macro_data.py`)
    **import these functions** rather than recomputing their own copies, and the
    API service imports them too. The equality assertions in
    `tests/strategy/test_macro_features.py` (vs. the engine) therefore now verify
    that wiring stays behaviour-preserving, and `tests/strategy/test_signals.py`
    locks the engine's public columns — neither test is modified by this refactor.

Units (carried in docstrings here; the API layer attaches `meta.unit` later):
  * **YoY / inflation values are decimal fractions** (e.g. ``0.031`` for 3.1%),
    *not* percentages — this matches the engine exactly (decision #3) and the
    app's existing ``formatPercent`` convention, which renders a fraction as a
    percent. (This deliberately departs from the spec's literal "× 100"; the
    engine pin takes precedence.)
  * **Yields and ``curve_spread`` stay in their native percentage points** as
    stored (``gs10``/``gs2`` are already in percent; ``curve_spread = gs10 - gs2``
    matches the engine's ``yield_curve``).
  * ``real_policy_rate = fed_funds - core_cpi_yoy * 100`` — ``fed_funds`` is in
    percent and ``core_cpi_yoy`` is a decimal fraction, so the ``* 100`` converts
    the fraction to percentage points before subtracting (engine line 25). It
    uses **core** CPI YoY, not headline.

`fill_method=None` is passed to every ``pct_change`` (matching the engine) so a
gap is never silently forward-filled — that would leak a stale value forward.
"""

from __future__ import annotations

import pandas as pd

# Raw macro_data columns this module reads. `pmi` is actually CFNAI (spec §3.2
# #2) — surfaced here as the activity series under its true meaning.
_REQUIRED_COLUMNS = ("date", "cpi", "core_cpi", "unemployment", "fed_funds", "gs2", "gs10", "pmi")

# 12 monthly observations = one year; 3/6 month windows for momentum.
_YOY_PERIODS = 12


def compute_cpi_features(cpi_index: pd.Series) -> pd.DataFrame:
    """Inflation features from a CPI *index level* series (monthly).

    Returns a frame (indexed like the input) with:
      * ``cpi_yoy`` — year-over-year change, a **decimal fraction**
        (``pct_change(12)``); matches the engine's ``cpi_yoy``.
      * ``cpi_yoy_change_3m`` — 3-month change in ``cpi_yoy`` (fraction diff).
      * ``cpi_yoy_acceleration`` — second difference of ``cpi_yoy``
        (``diff().diff()``); matches the engine's ``cpi_yoy_acceleration``.

    Works for headline or core CPI (caller renames as needed).
    """
    cpi_yoy = cpi_index.pct_change(periods=_YOY_PERIODS, fill_method=None)
    return pd.DataFrame(
        {
            "cpi_yoy": cpi_yoy,
            "cpi_yoy_change_3m": cpi_yoy.diff(3),
            "cpi_yoy_acceleration": cpi_yoy.diff().diff(),
        }
    )


def compute_activity_features(cfnai: pd.Series) -> pd.DataFrame:
    """Activity features from the CFNAI series (the raw ``pmi`` column, §3.2 #2).

    CFNAI is centred on **0** (neutral = trend growth), not 50. Returns:
      * ``activity_level`` — the level as-is (neutral 0).
      * ``activity_change_3m`` — 3-month change in the level.
    """
    return pd.DataFrame(
        {
            "activity_level": cfnai.astype("float64"),
            "activity_change_3m": cfnai.diff(3),
        }
    )


def compute_labour_features(unemployment: pd.Series) -> pd.DataFrame:
    """Labour features from the unemployment-rate series (percent, monthly).

    Returns:
      * ``unemployment`` — the level as-is (percent).
      * ``unemployment_change_3m`` / ``unemployment_change_6m`` — 3/6-month change
        (percentage points).
      * ``unemployment_minus_12m_low`` — level minus its trailing-12-month minimum
        (a Sahm-rule-style "off the lows" gauge; ``>0`` and rising signals a
        weakening labour market). Needs a full 12-month window.
    """
    return pd.DataFrame(
        {
            "unemployment": unemployment.astype("float64"),
            "unemployment_change_3m": unemployment.diff(3),
            "unemployment_change_6m": unemployment.diff(6),
            "unemployment_minus_12m_low": unemployment
            - unemployment.rolling(window=12, min_periods=12).min(),
        }
    )


def compute_policy_features(fed_funds: pd.Series, core_cpi_yoy: pd.Series) -> pd.DataFrame:
    """Monetary-policy features.

    ``core_cpi_yoy`` must be the **decimal-fraction** core CPI YoY (e.g. from
    :func:`compute_cpi_features` on ``core_cpi``). Returns:
      * ``fed_funds`` — the policy rate as-is (percent).
      * ``fed_funds_change_3m`` — 3-month change (percentage points).
      * ``real_policy_rate`` — ``fed_funds - core_cpi_yoy * 100`` (percentage
        points); positive = restrictive. Matches the engine exactly.
    """
    return pd.DataFrame(
        {
            "fed_funds": fed_funds.astype("float64"),
            "fed_funds_change_3m": fed_funds.diff(3),
            "real_policy_rate": fed_funds - (core_cpi_yoy * 100),
        }
    )


def compute_yield_curve_features(gs2: pd.Series, gs10: pd.Series) -> pd.DataFrame:
    """Yield-curve level and change features (yields in percent, monthly here).

    Returns:
      * ``gs2`` / ``gs10`` — the 2y/10y yields as-is (percent).
      * ``curve_spread`` — ``gs10 - gs2`` (percentage points); matches the
        engine's ``yield_curve``. Negative = inverted.
      * ``yield_2y_change_1m`` / ``yield_2y_change_3m`` — 1/3-month change in the
        2y yield (percentage points; the API may present these as basis points).
      * ``yield_10y_change_1m`` / ``yield_10y_change_3m`` — same for the 10y.
      * ``curve_spread_change_3m`` — 3-month change in the spread.
    """
    curve_spread = gs10 - gs2
    return pd.DataFrame(
        {
            "gs2": gs2.astype("float64"),
            "gs10": gs10.astype("float64"),
            "curve_spread": curve_spread,
            "yield_2y_change_1m": gs2.diff(1),
            "yield_2y_change_3m": gs2.diff(3),
            "yield_10y_change_1m": gs10.diff(1),
            "yield_10y_change_3m": gs10.diff(3),
            "curve_spread_change_3m": curve_spread.diff(3),
        }
    )


# --------------------------------------------------------------------------- #
# Yield-curve regime classification (Phase 2)
# --------------------------------------------------------------------------- #
# Canonical bond-curve regimes from the joint move of the 2y (short) and 10y
# (long) yields over a lookback. "Bull/bear" = yields falling/rising; "steepening
# /flattening" = the 10Y-2Y spread widening/narrowing (steepening ⟺ Δ10y > Δ2y).
# A twist (the two ends moving in opposite directions) is "Mixed".
CURVE_REGIMES: dict[int, str] = {
    0: "Bull steepening",
    1: "Bull flattening",
    2: "Bear flattening",
    3: "Bear steepening",
    4: "Mixed",
}
_CURVE_REGIME_CODE: dict[str, int] = {label: code for code, label in CURVE_REGIMES.items()}


def classify_curve_regime(delta_2y: float, delta_10y: float) -> str:
    """Classify a curve move from the 2y/10y yield changes over a lookback.

    Returns one of :data:`CURVE_REGIMES`' labels. Both ends must move the same
    way for a directional (bull/bear) label; opposite-sign moves (a twist) are
    "Mixed". Within a direction, steepening ⟺ the spread widens (Δ10y > Δ2y).
    """
    falling = delta_2y < 0 and delta_10y < 0
    rising = delta_2y > 0 and delta_10y > 0
    if not (falling or rising):
        return "Mixed"
    steepening = delta_10y > delta_2y  # 10Y-2Y spread widening
    if falling:
        return "Bull steepening" if steepening else "Bull flattening"
    return "Bear steepening" if steepening else "Bear flattening"


def compute_curve_regime(gs2: pd.Series, gs10: pd.Series, lookback: int = 3) -> pd.DataFrame:
    """Per-date curve regime from the yield changes over ``lookback`` periods.

    Returns a frame (indexed like the inputs) with ``curve_regime_code`` (the
    ordinal :data:`CURVE_REGIMES` code, ``NaN`` where the lookback is incomplete)
    and ``curve_regime`` (the label, ``None`` where incomplete).
    """
    d2 = gs2.diff(lookback)
    d10 = gs10.diff(lookback)
    codes: list[float] = []
    labels: list[str | None] = []
    for a, b in zip(d2, d10):
        if pd.isna(a) or pd.isna(b):
            codes.append(float("nan"))
            labels.append(None)
        else:
            label = classify_curve_regime(a, b)
            codes.append(float(_CURVE_REGIME_CODE[label]))
            labels.append(label)
    return pd.DataFrame({"curve_regime_code": codes, "curve_regime": labels}, index=gs2.index)


def inversion_intervals(dates: pd.Series, spread: pd.Series) -> list[dict[str, str]]:
    """Contiguous spans where the 10Y-2Y ``spread`` is inverted (< 0).

    Returns ``[{"start": ISO, "end": ISO}, ...]`` for shading on the chart. Each
    span runs over consecutive inverted observations (monthly here).
    """
    mask = (spread < 0).fillna(False).to_numpy()
    ts = pd.to_datetime(dates).to_numpy()
    spans: list[dict[str, str]] = []
    i, n = 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            spans.append(
                {
                    "start": pd.Timestamp(ts[i]).strftime("%Y-%m-%d"),
                    "end": pd.Timestamp(ts[j]).strftime("%Y-%m-%d"),
                }
            )
            i = j + 1
        else:
            i += 1
    return spans


def derive_macro_features(macro_df: pd.DataFrame) -> pd.DataFrame:
    """Derive all Phase-1 macro features from a raw ``macro_data`` frame.

    Orchestrates the per-domain helpers above. The input is the frame returned by
    ``db_reader.get_macro_history`` (raw monthly columns). The result is sorted by
    ``date`` (ascending, index reset — like the engine) and carries ``date`` plus
    every derived column. Headline-CPI columns keep their generic names
    (``cpi_yoy``, ``cpi_yoy_change_3m``, ``cpi_yoy_acceleration``); core-CPI
    columns are prefixed ``core_`` (``core_cpi_yoy`` …).

    The input frame is **not** mutated.

    Raises:
        ValueError: if any required raw column is missing.
    """
    missing = [c for c in _REQUIRED_COLUMNS if c not in macro_df.columns]
    if missing:
        raise ValueError(f"macro_df is missing required column(s): {missing}")

    df = macro_df.sort_values("date").reset_index(drop=True)

    headline = compute_cpi_features(df["cpi"])
    core = compute_cpi_features(df["core_cpi"]).add_prefix("core_")  # -> core_cpi_yoy, ...
    activity = compute_activity_features(df["pmi"])
    labour = compute_labour_features(df["unemployment"])
    policy = compute_policy_features(df["fed_funds"], core["core_cpi_yoy"])
    curve = compute_yield_curve_features(df["gs2"], df["gs10"])

    return pd.concat(
        [df[["date"]], headline, core, activity, labour, policy, curve],
        axis=1,
    )


# --------------------------------------------------------------------------- #
# Macro-regime classification (Phase 4)
# --------------------------------------------------------------------------- #
# A transparent, rule-based **dashboard-only** macro regime — distinct from the
# engine's allocation regimes (`monetary_regime`/`economic_regime` in
# src/decision/regime_engine.py). It is explanatory, chosen on economic priors,
# NOT fitted for return, and must not be wired into allocation.
MACRO_REGIMES: dict[int, str] = {
    0: "Stable Growth",
    1: "Inflationary Tightening",
    2: "Disinflationary Slowdown",
    3: "Stagflation Risk",
    4: "Easing Transition",
}
_MACRO_REGIME_CODE: dict[str, int] = {label: code for code, label in MACRO_REGIMES.items()}

# Expected bond preference per regime — an economic PRIOR (flagged as such for the
# legend), not a backtested result.
MACRO_REGIME_PRIORS: dict[str, str] = {
    "Stable Growth": "Balanced — intermediate AGG typically favoured.",
    "Inflationary Tightening": "Defensive — SHY > AGG > TLT (short duration).",
    "Disinflationary Slowdown": "Duration-friendly — TLT > AGG > SHY.",
    "Stagflation Risk": "Capital preservation — SHY / cash-like.",
    "Easing Transition": "Adding duration — increasing TLT.",
}

_HIGH_INFLATION = 0.03      # cpi_yoy (decimal) above ~3% = elevated
_INFL_CHANGE_EPS = 0.0005   # cpi_yoy 3m-change deadband (~0.05pp) to ignore noise
_RATE_CHANGE_EPS = 0.05     # fed-funds 3m-change deadband (~5bp)


def classify_macro_regime(
    *,
    cpi_yoy: float,
    cpi_yoy_change_3m: float,
    activity_level: float,
    activity_change_3m: float,
    unemployment_change_3m: float,
    fed_funds_change_3m: float,
    real_policy_rate: float,
    yield_2y_change_3m: float,
) -> str:
    """Classify one period into a dashboard macro regime (see :data:`MACRO_REGIMES`).

    Priority-ordered rules over the derived features (all keyword args; the four
    load-bearing ones — ``cpi_yoy``, ``cpi_yoy_change_3m``, ``activity_level``,
    ``fed_funds_change_3m`` — must be finite, the rest may be NaN and are treated
    as "no signal"). Thresholds are economic priors, not fitted.
    """
    inflation_rising = cpi_yoy_change_3m > _INFL_CHANGE_EPS
    inflation_falling = cpi_yoy_change_3m < -_INFL_CHANGE_EPS
    high_inflation = cpi_yoy > _HIGH_INFLATION
    growth_weak = activity_level < 0 or (not pd.isna(activity_change_3m) and activity_change_3m < 0)
    labour_weakening = not pd.isna(unemployment_change_3m) and unemployment_change_3m > 0
    fed_tightening = fed_funds_change_3m > _RATE_CHANGE_EPS
    fed_easing = fed_funds_change_3m < -_RATE_CHANGE_EPS
    restrictive = not pd.isna(real_policy_rate) and real_policy_rate > 0
    short_falling = not pd.isna(yield_2y_change_3m) and yield_2y_change_3m < 0

    # Elevated inflation while growth weakens and the Fed can't ease.
    if high_inflation and growth_weak and not fed_easing:
        return "Stagflation Risk"
    # Inflation accelerating into a tightening / restrictive stance, growth intact.
    if inflation_rising and (fed_tightening or restrictive) and not growth_weak:
        return "Inflationary Tightening"
    # Fed actively cutting with the front end falling and inflation contained.
    if fed_easing and short_falling and not high_inflation:
        return "Easing Transition"
    # Inflation cooling alongside weakening growth / labour.
    if inflation_falling and (growth_weak or labour_weakening):
        return "Disinflationary Slowdown"
    return "Stable Growth"


def compute_macro_regime(features: pd.DataFrame) -> pd.DataFrame:
    """Per-date dashboard macro regime from a derived-features frame.

    ``features`` is the output of :func:`derive_macro_features`. Returns a frame
    (indexed like ``features``) with ``macro_regime_code`` (ordinal
    :data:`MACRO_REGIMES` code, ``NaN`` where load-bearing inputs are missing) and
    ``macro_regime`` (label, ``None`` where missing).
    """
    required = ("cpi_yoy", "cpi_yoy_change_3m", "activity_level", "fed_funds_change_3m")
    codes: list[float] = []
    labels: list[str | None] = []
    for _, row in features.iterrows():
        if any(pd.isna(row.get(col)) for col in required):
            codes.append(float("nan"))
            labels.append(None)
            continue
        label = classify_macro_regime(
            cpi_yoy=row["cpi_yoy"],
            cpi_yoy_change_3m=row["cpi_yoy_change_3m"],
            activity_level=row["activity_level"],
            activity_change_3m=row.get("activity_change_3m"),
            unemployment_change_3m=row.get("unemployment_change_3m"),
            fed_funds_change_3m=row["fed_funds_change_3m"],
            real_policy_rate=row.get("real_policy_rate"),
            yield_2y_change_3m=row.get("yield_2y_change_3m"),
        )
        codes.append(float(_MACRO_REGIME_CODE[label]))
        labels.append(label)
    return pd.DataFrame({"macro_regime_code": codes, "macro_regime": labels}, index=features.index)


# --------------------------------------------------------------------------- #
# Conditional forward-return analysis (Phase 5)
# --------------------------------------------------------------------------- #
def compute_forward_returns(prices: pd.Series, horizons: dict[str, int]) -> pd.DataFrame:
    """Forward total return over each horizon (rows ahead), strictly future-looking.

    For each row ``i`` and horizon ``h``: ``prices[i + h] / prices[i] - 1``. Rows
    without a full horizon ahead (the tail) stay ``NaN`` — no future info leaks
    into the conditioning row, and no past info is used. ``horizons`` maps a name
    to a number of rows/periods ahead (trading days for a daily price series).
    """
    out = {name: prices.shift(-h) / prices - 1.0 for name, h in horizons.items()}
    return pd.DataFrame(out, index=prices.index)


def macro_availability_dates(reference_dates: pd.Series) -> pd.Series:
    """Conservative point-in-time *availability* proxy: reference month-end + 1 month.

    ``macro_data`` dates are FRED reference month-starts, not release dates. To
    avoid look-ahead when conditioning forward returns we only treat a monthly
    reading as knowable ~1 month after its month ends (decision #4).

    **Accepted debt:** this flat shift is a placeholder for a future
    forecasting/nowcasting model of what was actually knowable at time ``t`` — not
    a per-series publication-lag table.
    """
    d = pd.to_datetime(reference_dates)
    return d + pd.offsets.MonthEnd(0) + pd.DateOffset(months=1)


def build_conditional_forward_return_table(
    df: pd.DataFrame, regime_col: str, return_cols: list[str]
) -> pd.DataFrame:
    """Per-regime aggregates of forward returns (one row per regime).

    For each forward-return column: ``mean``, ``median``, ``hit`` (fraction > 0),
    and ``count`` (non-null observations); plus ``n`` (conditioning rows in the
    regime). Pure: no row multiplication, ``NaN`` forward returns excluded per
    column. Descriptive only — overlapping horizons make observations
    non-independent (the caller surfaces that caveat).
    """
    records: list[dict] = []
    for regime, grp in df.groupby(regime_col, sort=True):
        rec: dict = {regime_col: regime, "n": int(len(grp))}
        for col in return_cols:
            vals = grp[col].dropna()
            count = int(len(vals))
            rec[f"{col}_mean"] = float(vals.mean()) if count else float("nan")
            rec[f"{col}_median"] = float(vals.median()) if count else float("nan")
            rec[f"{col}_hit"] = float((vals > 0).mean()) if count else float("nan")
            rec[f"{col}_count"] = count
        records.append(rec)
    return pd.DataFrame(records)
