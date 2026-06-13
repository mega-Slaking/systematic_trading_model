"""Returns-diagnostic service (Returns Analysis redesign).

Turns the dense all-scenario daily-return scatter into a focused *diagnostic*
payload: a small set of selected scenarios, enriched per point with the context
needed to explain an unusual return (NAV, weights, primary holding, regime,
turnover, cost), plus the worst/best/dispersion tables and the distribution data
the boxplot needs.

Per the design spec (docs/returns_analysis_diagnostic_redesign_spec.md) every
dataframe transform lives here in the Python service tier (unit-tested under
``api/tests/test_returns_diagnostics.py``); the React side only renders the
serialized payload. We reuse the canonical readers in ``src/storage/db_reader``
and the §6 serialization boundary -- no schema changes, no new dependencies.
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

import re

import numpy as np
import pandas as pd

from accounting.tearsheet_calculator import parse_weights
from src.storage.db_reader import (
    get_backtest_regime_trace,
    get_backtest_results,
    get_scenario_ids,
)

from api.schemas.backtest import ReturnsPointDetail, ScenarioMeta
from api.serialization.frames import df_to_table, nan_to_none, to_iso

# Assets the long-only bond-rotation strategy trades; surfaced as explicit
# per-asset weight columns in the diagnostic frame / tables / hover.
_WEIGHT_TICKERS: tuple[str, ...] = ("TLT", "AGG", "SHY")

# Round the dense per-point returns to trim wire size (matches get_returns, §6).
_RETURNS_ROUND_DP = 8

# Return-filter modes the chart offers (kept in sync with the React control).
FILTER_MODES: tuple[str, ...] = (
    "all",
    "abs_gt_1pct",
    "abs_gt_2pct",
    "worst_1pct",
    "best_1pct",
    "extremes_20",
)

# Deterministic, representative default selection (spec §"Scenario Selector").
# Intersected with what actually exists, capped at five, order preserved. Summary
# metrics (best Sharpe/CAGR) are deliberately *not* computed here -- that would
# mean a per-scenario tearsheet build on every page load; the spec lists this
# representative fallback as acceptable.
_PREFERRED_DEFAULTS: tuple[str, ...] = (
    "default",
    "baseV1_roll20",
    "baseV1_roll20_covlb20_tv03",
    "baseV1_roll20_ewmacov_lam94_tv03",
    "legacyBase_roll20_ewmacov_lam94_tv03",
    "legacyBase_roll20",
)
_MAX_DEFAULT_SCENARIOS = 5
# Scenarios drawn *visible* on first load; the rest start ``legendonly`` and are
# toggled in via the Plotly legend (client-side, no refetch).
_DEFAULT_VISIBLE_COUNT = 3

# Human family labels for the scenario-id prefix.
_FAMILY_LABELS: dict[str, str] = {
    "baseV1": "Base",
    "legacyBase": "Legacy",
    "default": "Default",
}

# Volatility-method tokens -> (machine value, human label).
_VOL_METHODS: dict[str, tuple[str, str]] = {
    "ewmacov": ("ewmacov", "EWMA covariance"),
    "covlb": ("covlb", "Covariance lookback"),
    "roll": ("roll", "Rolling"),
}


# --------------------------------------------------------------------------- #
# Scenario-id parsing  (pure, defensive -- never raises)
# --------------------------------------------------------------------------- #
def parse_scenario_metadata(scenario_id: str) -> dict:
    """Extract scenario metadata from its id; unknown components stay ``None``.

    Permissive by design: an unparseable or partial id yields ``None`` fields
    rather than raising (the family/vol-method/target-vol filters degrade
    gracefully). Example::

        baseV1_roll20_ewmacov_lam94_tv03 -> {
            "family": "baseV1", "lookback": 20, "vol_method": "ewmacov",
            "cov_lookback": None, "ewma_lambda": 0.94, "target_vol": 0.03,
        }
    """
    meta: dict = {
        "family": None,
        "lookback": None,
        "vol_method": None,
        "cov_lookback": None,
        "ewma_lambda": None,
        "target_vol": None,
    }
    if not isinstance(scenario_id, str) or not scenario_id:
        return meta

    tokens = scenario_id.split("_")
    meta["family"] = tokens[0] or None

    has_covlb = False
    has_ewmacov = False
    for tok in tokens[1:]:
        if (m := re.fullmatch(r"roll(\d+)", tok)):
            meta["lookback"] = int(m.group(1))
        elif (m := re.fullmatch(r"covlb(\d+)", tok)):
            meta["cov_lookback"] = int(m.group(1))
            has_covlb = True
        elif tok == "ewmacov":
            has_ewmacov = True
        elif (m := re.fullmatch(r"lam(\d+)", tok)):
            # lam94 -> 0.94, lam97 -> 0.97 (two-digit lambda convention).
            digits = m.group(1)
            meta["ewma_lambda"] = float(f"0.{digits}") if digits else None
        elif (m := re.fullmatch(r"tv(\d+)", tok)):
            # tv03 -> 0.03, tv05 -> 0.05 (whole-percent target vol).
            meta["target_vol"] = int(m.group(1)) / 100.0

    if has_ewmacov:
        meta["vol_method"] = "ewmacov"
    elif has_covlb:
        meta["vol_method"] = "covlb"
    elif meta["lookback"] is not None:
        meta["vol_method"] = "roll"

    return meta


def format_scenario_label(scenario_id: str) -> str:
    """Convert a raw scenario id into a concise readable label.

    Examples::

        default                                   -> Default
        baseV1_roll20                             -> Base / Roll 20
        baseV1_roll20_covlb20_tv03                -> Base / Cov LB 20 / TV 3%
        baseV1_roll20_ewmacov_lam94_tv05          -> Base / EWMA λ94 / TV 5%
        legacyBase_roll20_ewmacov_lam97_tv04      -> Legacy / EWMA λ97 / TV 4%

    Safe fallback: anything that does not parse returns the raw id unchanged, so
    a label failure can never break the page.
    """
    if not isinstance(scenario_id, str) or not scenario_id:
        return scenario_id

    try:
        meta = parse_scenario_metadata(scenario_id)
        family = meta["family"]
        segments: list[str] = [_FAMILY_LABELS.get(family, family)] if family else []

        # Method segment: EWMA / Cov LB take precedence over the plain rolling lookback.
        if meta["vol_method"] == "ewmacov" and meta["ewma_lambda"] is not None:
            segments.append(f"EWMA λ{_lambda_digits(meta['ewma_lambda'])}")
        elif meta["vol_method"] == "covlb" and meta["cov_lookback"] is not None:
            segments.append(f"Cov LB {meta['cov_lookback']}")
        elif meta["lookback"] is not None:
            segments.append(f"Roll {meta['lookback']}")

        if meta["target_vol"] is not None:
            segments.append(f"TV {_percent_label(meta['target_vol'])}")

        # Preserve any tokens we did not recognise (e.g. baseV1_roll20_p005) so
        # otherwise-identical labels never collide in the legend.
        for tok in _unrecognised_tokens(scenario_id):
            segments.append(tok)

        label = " / ".join(s for s in segments if s)
        return label or scenario_id
    except Exception:  # pragma: no cover - defensive; parsing must never break rendering
        return scenario_id


def _lambda_digits(ewma_lambda: float) -> str:
    """0.94 -> "94" for the EWMA label (drop the leading "0.")."""
    return f"{ewma_lambda:.2f}".split(".")[-1]


def _percent_label(fraction: float) -> str:
    """0.03 -> "3%", 0.025 -> "2.5%" (trim a trailing .0)."""
    pct = fraction * 100.0
    text = f"{pct:.1f}".rstrip("0").rstrip(".")
    return f"{text}%"


def _unrecognised_tokens(scenario_id: str) -> list[str]:
    """Tokens after the family that none of the known patterns consumed."""
    known = re.compile(r"roll\d+|covlb\d+|ewmacov|lam\d+|tv\d+")
    return [tok for tok in scenario_id.split("_")[1:] if not known.fullmatch(tok)]


def scenario_meta(scenario_id: str) -> ScenarioMeta:
    """Bundle a scenario's readable label + parsed metadata for the UI filters."""
    meta = parse_scenario_metadata(scenario_id)
    return ScenarioMeta(
        scenario_id=scenario_id,
        scenario_label=format_scenario_label(scenario_id),
        family=meta["family"],
        lookback=meta["lookback"],
        vol_method=meta["vol_method"],
        cov_lookback=meta["cov_lookback"],
        ewma_lambda=meta["ewma_lambda"],
        target_vol=meta["target_vol"],
    )


def default_scenario_selection(available: list[str], limit: int = _MAX_DEFAULT_SCENARIOS) -> list[str]:
    """Pick the representative scenarios visible by default from those that exist.

    The page now fetches *all* scenarios and toggles visibility via the Plotly
    legend (no refetch), so this only decides which handful render visible on
    first load; the rest start ``legendonly``.
    """
    available_set = set(available)
    chosen = [sid for sid in _PREFERRED_DEFAULTS if sid in available_set]
    if len(chosen) < min(limit, len(available)):
        # Pad with whatever exists (preserving order) so a thin DB still renders.
        for sid in available:
            if sid not in chosen:
                chosen.append(sid)
            if len(chosen) >= limit:
                break
    return chosen[:limit]


# --------------------------------------------------------------------------- #
# Primary holding  (pure)
# --------------------------------------------------------------------------- #
def determine_primary_holding(weights: dict | None) -> str | None:
    """Return the asset with the largest *absolute* weight (long/short safe).

    ``Cash`` when every weight is ~zero; ``None`` when weights are unavailable.
    """
    if not weights:
        return None
    items = [(asset, w) for asset, w in weights.items() if w is not None]
    if not items:
        return None
    asset, weight = max(items, key=lambda kv: abs(kv[1]))
    if abs(weight) < 1e-9:
        return "Cash"
    return asset


# --------------------------------------------------------------------------- #
# Diagnostic frame  (enrichment via left joins -- missing context never drops a row)
# --------------------------------------------------------------------------- #
def build_returns_diagnostic_frame(
    results_df: pd.DataFrame,
    regime_trace_df: pd.DataFrame | None = None,
    asset_prices_df: pd.DataFrame | None = None,  # reserved: per-asset returns (optional)
) -> pd.DataFrame:
    """Build the enriched daily-return diagnostic dataframe.

    Required: ``results_df`` from ``get_backtest_results`` (carries ``ret``,
    ``nav``, ``weights``, ``turnover``, ``total_cost``, ``top_asset``). NAV,
    weights, turnover and cost are already columns there -- only the regime
    context is a separate left-join (on ``["date", "scenario_id"]``, the same key
    ``tearsheet.py`` uses). ``ret`` is renamed ``daily_return`` for clarity.

    ``asset_prices_df`` is accepted for forward-compatibility (deriving per-asset
    return context) but is optional and unused in the first pass.
    """
    cols = [
        "date",
        "scenario_id",
        "daily_return",
        "nav",
        "tlt_weight",
        "agg_weight",
        "shy_weight",
        "primary_holding",
        "turnover",
        "total_cost",
        "scenario_label",
        "inflation_regime",
        "growth_regime",
        "labour_regime",
        "curve_state",
        "macro_supports_duration",
    ]
    if results_df is None or results_df.empty:
        return pd.DataFrame(columns=cols)

    df = results_df.copy()
    df = df.rename(columns={"ret": "daily_return"})

    # Per-asset weights + primary holding from the JSON ``weights`` column.
    if "weights" in df.columns:
        parsed = df["weights"].map(parse_weights)
        for ticker in _WEIGHT_TICKERS:
            df[f"{ticker.lower()}_weight"] = parsed.map(lambda w, t=ticker: w.get(t))
        # Prefer the persisted dominant holding; fall back to the parsed weights.
        top = df.get("top_asset")
        df["primary_holding"] = [
            (ta if isinstance(ta, str) and ta else determine_primary_holding(w))
            for ta, w in zip(top if top is not None else [None] * len(df), parsed)
        ]
    else:
        for ticker in _WEIGHT_TICKERS:
            df[f"{ticker.lower()}_weight"] = None
        df["primary_holding"] = None

    df["scenario_label"] = df["scenario_id"].map(format_scenario_label)

    # Left-join the regime trace; absent context leaves nulls, never drops a row.
    regime_cols = [
        "inflation_regime",
        "growth_regime",
        "labour_regime",
        "curve_state",
        "macro_supports_duration",
    ]
    if regime_trace_df is not None and not regime_trace_df.empty:
        keep = ["date", "scenario_id"] + [c for c in regime_cols if c in regime_trace_df.columns]
        df = df.merge(regime_trace_df[keep], on=["date", "scenario_id"], how="left")
    for col in regime_cols:
        if col not in df.columns:
            df[col] = None

    for col in cols:
        if col not in df.columns:
            df[col] = None
    return df[cols]


# --------------------------------------------------------------------------- #
# View filtering  (scenario + date + return-filter mode)
# --------------------------------------------------------------------------- #
def filter_returns_for_view(
    df: pd.DataFrame,
    selected_scenarios: list[str],
    start_date: pd.Timestamp | None,
    end_date: pd.Timestamp | None,
    filter_mode: str,
) -> pd.DataFrame:
    """Apply scenario, date-range, and return-filter selections (in that order)."""
    if df.empty:
        return df

    out = df[df["scenario_id"].isin(selected_scenarios)]
    if start_date is not None:
        out = out[out["date"] >= start_date]
    if end_date is not None:
        out = out[out["date"] <= end_date]

    out = _apply_return_filter(out, filter_mode)
    return out.reset_index(drop=True)


def _apply_return_filter(df: pd.DataFrame, filter_mode: str) -> pd.DataFrame:
    """Subset rows by the chosen return-filter mode (per-scenario where stated)."""
    if df.empty or filter_mode == "all":
        return df
    ret = df["daily_return"]

    if filter_mode == "abs_gt_1pct":
        return df[ret.abs() > 0.01]
    if filter_mode == "abs_gt_2pct":
        return df[ret.abs() > 0.02]

    grouped = df.groupby("scenario_id")["daily_return"]
    if filter_mode == "worst_1pct":
        thresh = grouped.transform(lambda s: s.quantile(0.01))
        return df[ret <= thresh]
    if filter_mode == "best_1pct":
        thresh = grouped.transform(lambda s: s.quantile(0.99))
        return df[ret >= thresh]
    if filter_mode == "extremes_20":
        # 20 highest + 20 lowest per scenario; nlargest/nsmallest tolerate < 20.
        idx: list = []
        for _, s in df.groupby("scenario_id")["daily_return"]:
            idx.extend(s.nlargest(20).index.tolist())
            idx.extend(s.nsmallest(20).index.tolist())
        return df.loc[sorted(set(idx))]

    # Unknown mode -> no extra filtering (defensive).
    return df


# --------------------------------------------------------------------------- #
# Diagnostic tables  (worst / best / dispersion)
# --------------------------------------------------------------------------- #
# Columns surfaced in the worst/best tables (order matters for display).
_RETURN_TABLE_COLUMNS: tuple[str, ...] = (
    "date",
    "scenario_label",
    "scenario_id",
    "daily_return",
    "primary_holding",
    "tlt_weight",
    "agg_weight",
    "shy_weight",
    "growth_regime",
    "curve_state",
    "macro_supports_duration",
    "turnover",
    "total_cost",
)


def _return_table(df: pd.DataFrame, *, ascending: bool, limit: int) -> pd.DataFrame:
    """Shared worst/best builder: sort by daily_return, take ``limit`` rows."""
    if df.empty:
        return pd.DataFrame(columns=list(_RETURN_TABLE_COLUMNS))
    ranked = df.sort_values("daily_return", ascending=ascending).head(limit)
    keep = [c for c in _RETURN_TABLE_COLUMNS if c in ranked.columns]
    out = ranked[keep].copy()
    if "macro_supports_duration" in out.columns:
        out["macro_supports_duration"] = out["macro_supports_duration"].map(_yes_no)
    return out.reset_index(drop=True)


def build_worst_returns_table(df: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """The most severe daily losses across selected scenarios (ascending)."""
    return _return_table(df, ascending=True, limit=limit)


def build_best_returns_table(df: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """The largest daily gains across selected scenarios (descending)."""
    return _return_table(df, ascending=False, limit=limit)


_DISPERSION_COLUMNS: tuple[str, ...] = (
    "date",
    "dispersion",
    "best_scenario_label",
    "best_scenario_id",
    "best_return",
    "worst_scenario_label",
    "worst_scenario_id",
    "worst_return",
    "scenario_count",
)


def build_scenario_dispersion_table(df: pd.DataFrame, limit: int = 20) -> pd.DataFrame:
    """Dates where scenario choice mattered most: ``max(ret) - min(ret)`` per date.

    Dates with fewer than two scenario observations are excluded (dispersion is
    undefined for a single curve).
    """
    if df.empty:
        return pd.DataFrame(columns=list(_DISPERSION_COLUMNS))

    valid = df.dropna(subset=["daily_return"]).reset_index(drop=True)
    if valid.empty:
        return pd.DataFrame(columns=list(_DISPERSION_COLUMNS))

    # Vectorized per-date aggregation -- a Python groupby loop over thousands of
    # dates (nunique / idxmax / .loc each iteration) was the endpoint's hot spot.
    grouped = valid.groupby("date")["daily_return"]
    by_date = pd.DataFrame(
        {
            "best_return": grouped.max(),
            "worst_return": grouped.min(),
            "scenario_count": valid.groupby("date")["scenario_id"].nunique(),
            "best_idx": grouped.idxmax(),
            "worst_idx": grouped.idxmin(),
        }
    )
    by_date = by_date[by_date["scenario_count"] >= 2]  # dispersion needs >= 2 curves
    if by_date.empty:
        return pd.DataFrame(columns=list(_DISPERSION_COLUMNS))

    by_date["dispersion"] = by_date["best_return"] - by_date["worst_return"]
    best_rows = valid.loc[by_date["best_idx"].to_numpy()]
    worst_rows = valid.loc[by_date["worst_idx"].to_numpy()]
    out = pd.DataFrame(
        {
            "date": by_date.index,
            "dispersion": by_date["dispersion"].to_numpy(),
            "best_scenario_label": best_rows["scenario_label"].to_numpy(),
            "best_scenario_id": best_rows["scenario_id"].to_numpy(),
            "best_return": by_date["best_return"].to_numpy(),
            "worst_scenario_label": worst_rows["scenario_label"].to_numpy(),
            "worst_scenario_id": worst_rows["scenario_id"].to_numpy(),
            "worst_return": by_date["worst_return"].to_numpy(),
            "scenario_count": by_date["scenario_count"].to_numpy().astype(int),
        },
        columns=list(_DISPERSION_COLUMNS),
    )
    return out.sort_values("dispersion", ascending=False).head(limit).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Hover text  (built server-side; missing fields omitted, never "None"/"NaN")
# --------------------------------------------------------------------------- #
def build_hover_lines(row) -> list[str]:
    """Assemble one point's diagnostic lines, omitting unavailable fields.

    Used for the click-drilldown panel (one point, fetched on demand) -- *not*
    shipped per-point for the whole grid, which would bloat the payload. Missing
    optional fields are skipped so nothing renders as ``None`` / ``NaN`` / ``null``.
    """
    lines: list[str] = []

    label = row.get("scenario_label")
    if isinstance(label, str) and label:
        lines.append(label)

    date = row.get("date")
    if pd.notna(date):
        lines.append(pd.Timestamp(date).strftime("%Y-%m-%d"))

    lines.append(f"Return: {_pct(row.get('daily_return'))}")

    nav = nan_to_none(row.get("nav"))
    if nav is not None:
        lines.append(f"NAV: {nav:,.0f}")

    weight_bits = [
        f"{t} {_pct(row.get(f'{t.lower()}_weight'), digits=0)}"
        for t in _WEIGHT_TICKERS
        if nan_to_none(row.get(f"{t.lower()}_weight")) is not None
    ]
    if weight_bits:
        lines.append("Weights: " + ", ".join(weight_bits))

    primary = row.get("primary_holding")
    if isinstance(primary, str) and primary:
        lines.append(f"Primary holding: {primary}")

    growth = row.get("growth_regime")
    if isinstance(growth, str) and growth:
        lines.append(f"Growth regime: {growth}")
    curve = row.get("curve_state")
    if isinstance(curve, str) and curve:
        lines.append(f"Curve state: {curve}")
    supports = _yes_no(row.get("macro_supports_duration"))
    if supports is not None:
        lines.append(f"Macro supports duration: {supports}")

    turnover = nan_to_none(row.get("turnover"))
    if turnover is not None:
        lines.append(f"Turnover: {_pct(turnover)}")
    cost = nan_to_none(row.get("total_cost"))
    if cost is not None:
        lines.append(f"Cost: {_pct(cost)}")

    sid = row.get("scenario_id")
    if isinstance(sid, str) and sid:
        lines.append(sid)

    return lines


def build_hover_text(row) -> str:
    """The drilldown lines joined for compact display/testing."""
    return "<br>".join(build_hover_lines(row))


def _pct(value, digits: int = 2) -> str:
    """Format a decimal fraction as a percent string; em-dash for missing."""
    clean = nan_to_none(value)
    if clean is None:
        return "—"
    return f"{float(clean) * 100:.{digits}f}%"


def _yes_no(value) -> str | None:
    """Map the stringy macro_supports_duration flag ('1'/'0') to Yes/No."""
    clean = nan_to_none(value)
    if clean is None or clean == "":
        return None
    text = str(clean).strip().lower()
    if text in {"1", "true", "yes"}:
        return "Yes"
    if text in {"0", "false", "no"}:
        return "No"
    return str(clean)


# --------------------------------------------------------------------------- #
# Serialization helpers
# --------------------------------------------------------------------------- #
def _round_returns(values) -> list[float | None]:
    """NaN/Inf -> None, finite floats rounded to trim wire size (§6).

    Vectorized: per-element ``pd.isna`` over tens of thousands of points was a
    measurable hot spot, so round + finite-mask with numpy and only materialize
    ``None`` for the non-finite cells.
    """
    arr = np.round(np.asarray(values, dtype="float64"), _RETURNS_ROUND_DP)
    out = arr.astype(object)
    out[~np.isfinite(arr)] = None
    return out.tolist()


# --------------------------------------------------------------------------- #
# Orchestration (the endpoint entry point)
# --------------------------------------------------------------------------- #
def get_returns_diagnostic(
    scenario_ids: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    filter_mode: str = "all",
    table_limit: int = 20,
) -> dict:
    """Assemble the full Returns Analysis diagnostic payload (all scenarios at once).

    Returns a plain ``dict`` (matching ``ReturnsDiagnosticResponse``) rather than
    the Pydantic model: the payload carries ~170k list elements, and per-element
    Pydantic validation measured ~3s -- the dominant cost -- whereas orjson
    encodes the equivalent dict in ~20ms. The router ships it via ``ORJSONResponse``
    (validation skipped; ``response_model`` still drives the OpenAPI schema/types).
    All non-finite floats are already mapped to ``None`` upstream, so the §6 JSON
    boundary holds.

    The whole scenario *universe* is shipped in one response so the page can
    toggle curve visibility via the Plotly legend with no further fetches;
    ``default_visible`` names the handful drawn visible on first load.

    - ``scenario_ids`` -- optional restriction of the universe; ``None`` -> every
      persisted scenario.
    - ``start`` / ``end`` -- ISO ``YYYY-MM-DD`` clamps (clipped to the data range).
    - ``filter_mode`` -- return-filter applied to the *scatter only*; the boxplot
      distribution and the diagnostic tables always span the full date range.
    """
    if filter_mode not in FILTER_MODES:
        filter_mode = "all"

    available = get_scenario_ids()
    available_scenarios = [scenario_meta(sid) for sid in available]

    requested = [s for s in (scenario_ids or []) if s in set(available)]
    universe = requested or available  # default: the whole grid
    default_visible = default_scenario_selection(universe, limit=_DEFAULT_VISIBLE_COUNT)

    results = get_backtest_results()
    date_min_ts = results["date"].min() if not results.empty else None
    date_max_ts = results["date"].max() if not results.empty else None
    results = results[results["scenario_id"].isin(universe)]

    # Lean frame for the scatter / distribution / dispersion: just the columns
    # those need (date, scenario_id, return, label). The expensive enrichment
    # (weights parse, regime join) is deferred to the few rows that land in the
    # worst/best tables -- enriching all ~86k rows to surface ~40 was the bottleneck.
    label_map = {sid: format_scenario_label(sid) for sid in universe}
    lean = pd.DataFrame(
        {
            "date": results["date"].to_numpy(),
            "scenario_id": results["scenario_id"].to_numpy(),
            "daily_return": results["ret"].to_numpy(),
        }
    )
    lean["scenario_label"] = lean["scenario_id"].map(label_map)

    start_ts = _clamp_date(start, date_min_ts, date_max_ts)
    end_ts = _clamp_date(end, date_min_ts, date_max_ts)

    # Scatter = universe + date + return-filter. Distribution/tables = date only.
    # The scatter ships only date+return per point (lean -> instant legend toggles,
    # no refetch); rich per-point context lives in the tables and the on-demand
    # click drilldown (``get_returns_point_detail``).
    scatter = filter_returns_for_view(lean, universe, start_ts, end_ts, filter_mode)
    in_range = filter_returns_for_view(lean, universe, start_ts, end_ts, "all")

    series: list[dict] = []
    distribution: list[dict] = []
    for sid in universe:
        label = label_map[sid]
        sdf = scatter[scatter["scenario_id"] == sid].sort_values("date")
        if not sdf.empty:
            series.append(
                {
                    "scenario_id": sid,
                    "scenario_label": label,
                    "dates": to_iso(sdf["date"]).tolist(),
                    "returns": _round_returns(sdf["daily_return"].tolist()),
                }
            )
        ddf = in_range[in_range["scenario_id"] == sid]
        if not ddf.empty:
            distribution.append(
                {
                    "scenario_id": sid,
                    "scenario_label": label,
                    "returns": _round_returns(ddf["daily_return"].tolist()),
                }
            )

    # Worst/best need the rich columns, but only for their top rows: take the
    # candidates from the lean frame, then enrich just those (<= 2*table_limit).
    enriched = _enrich_table_candidates(in_range, results, table_limit)

    return {
        "available_scenarios": [m.model_dump() for m in available_scenarios],
        "default_visible": default_visible,
        "date_min": to_iso(pd.Series([date_min_ts])).iloc[0] if date_min_ts is not None else None,
        "date_max": to_iso(pd.Series([date_max_ts])).iloc[0] if date_max_ts is not None else None,
        "filter_mode": filter_mode,
        "series": series,
        "distribution": distribution,
        "worst": df_to_table(build_worst_returns_table(enriched, table_limit)).model_dump(),
        "best": df_to_table(build_best_returns_table(enriched, table_limit)).model_dump(),
        "dispersion": df_to_table(build_scenario_dispersion_table(in_range, table_limit)).model_dump(),
    }


def _enrich_table_candidates(
    lean_in_range: pd.DataFrame,
    results: pd.DataFrame,
    table_limit: int,
) -> pd.DataFrame:
    """Build the rich diagnostic frame for *only* the worst/best candidate rows.

    Takes the worst + best ``table_limit`` returns from the lean (date-ranged)
    frame, looks their full rows up in ``results``, and enriches that small subset
    (weights parse + regime join). Avoids enriching the entire grid.
    """
    if lean_in_range.empty:
        return build_returns_diagnostic_frame(pd.DataFrame(), None)

    candidates = pd.concat(
        [
            lean_in_range.nsmallest(table_limit, "daily_return"),
            lean_in_range.nlargest(table_limit, "daily_return"),
        ]
    ).drop_duplicates(subset=["date", "scenario_id"])

    subset = results.merge(candidates[["date", "scenario_id"]], on=["date", "scenario_id"])
    regime = get_backtest_regime_trace()
    return build_returns_diagnostic_frame(subset, regime)


def get_returns_point_detail(scenario_id: str, date: str) -> ReturnsPointDetail:
    """Rich diagnostic detail for a single (scenario, date) -- the click drilldown.

    A one-row read so the main scatter payload can stay lean. Raises
    ``LookupError`` when the scenario or date has no observation.
    """
    target = pd.to_datetime(date, errors="coerce")
    if pd.isna(target):
        raise LookupError(f"{scenario_id} @ {date}")

    results = get_backtest_results(scenario_id)
    if results.empty:
        raise LookupError(scenario_id)
    results = results[results["date"] == target]
    if results.empty:
        raise LookupError(f"{scenario_id} @ {date}")

    regime = get_backtest_regime_trace(scenario_id)
    diag = build_returns_diagnostic_frame(results, regime)
    row = diag.iloc[0].to_dict()

    return ReturnsPointDetail(
        scenario_id=scenario_id,
        scenario_label=format_scenario_label(scenario_id),
        date=to_iso(pd.Series([target])).iloc[0],
        daily_return=nan_to_none(row.get("daily_return")),
        lines=build_hover_lines(row),
    )


def _clamp_date(
    value: str | None,
    lo: pd.Timestamp | None,
    hi: pd.Timestamp | None,
) -> pd.Timestamp | None:
    """Parse an ISO date and clip it to ``[lo, hi]``; ``None``/unparseable -> ``None``."""
    if not value:
        return None
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    if lo is not None and ts < lo:
        ts = lo
    if hi is not None and ts > hi:
        ts = hi
    return ts
