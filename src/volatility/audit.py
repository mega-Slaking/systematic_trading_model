"""Phase 0 — volatility-surface data contract: validation + normalization.

This module establishes a documented, tested contract for the persisted
``volatility_features`` surface *before* any interpretation logic (percentiles,
direction, states) is layered on in later phases. Nothing here computes a
derived feature; it only audits and normalizes the raw surface.

Public surface:

* :func:`validate_volatility_surface` — returns a list of *non-fatal*
  human-readable data-quality warnings. An empty list means the surface passed
  every check. It never raises on data content, so it is safe to call from an
  API debug endpoint without risking the response.
* :func:`normalize_volatility_surface` — returns a stable, canonically-ordered,
  correctly-typed frame for a *single* ``config_key``. It enforces the
  config_key-isolation contract (spec §4.3) by raising if the input mixes
  configs, because every downstream percentile/ratio would be wrong otherwise.
* :func:`surface_data_version` — the cache freshness token (spec §7) so later
  phases derive it consistently.

Contract summary (see ``docs/volatility_data_contract.md`` and design spec §4):

* The surface is **already lagged one day** in
  ``feature_surface._lag_feature_columns`` (applied exactly once). Derived
  features are never re-shifted.
* Annualized volatilities are stored as **decimals** (0.09 == 9%); display
  layers convert to percent.
* One row per ``(date, ticker)`` within a ``config_key``; the surface is
  scenario-independent.
* Warm-up ``NaN`` rows are expected and must survive to the JSON boundary as
  ``null`` — normalization never drops them.
"""

from __future__ import annotations

import pandas as pd

from src.volatility.constants import (
    COMPARISON_FEATURE_COLUMNS,
    CONFIG_KEY_COLUMN,
    SURFACE_KEY_COLUMNS,
    VOL_ESTIMATOR_NAMES,
)

# A non-NaN annualized-vol decimal above this is implausible (500% annualized) and
# almost certainly indicates percentage-scale values (e.g. 8.97 for 8.97%) or a
# data error. Used only for a soft warning, never to mutate data.
_DECIMAL_VOL_SANITY_CEILING = 5.0


def validate_volatility_surface(
    surface_df: pd.DataFrame,
    estimator_columns: list[str],
) -> list[str]:
    """Return non-fatal data-quality warnings for the persisted surface.

    Checks, in order: required key columns; presence of the requested estimator
    columns; duplicate ``(date, ticker[, config_key])`` rows; negative
    volatilities; per-ticker date monotonicity; multiple ``config_key`` values
    (isolation risk); and a decimals-not-percent scale heuristic. An empty list
    means the surface is clean. This function never raises on data content.
    """
    if surface_df is None or surface_df.empty:
        return ["surface is empty"]

    df = surface_df
    warnings: list[str] = []

    # 1. Required key columns.
    missing_keys = [c for c in SURFACE_KEY_COLUMNS if c not in df.columns]
    if missing_keys:
        warnings.append(f"missing key column(s): {missing_keys}")

    # 2. Requested estimator columns present.
    missing_est = [c for c in estimator_columns if c not in df.columns]
    if missing_est:
        warnings.append(f"missing estimator column(s): {missing_est}")

    present_est = [c for c in estimator_columns if c in df.columns]

    # 3. Duplicate keys (respecting config_key when present).
    if not missing_keys:
        dup_keys = list(SURFACE_KEY_COLUMNS)
        if CONFIG_KEY_COLUMN in df.columns:
            dup_keys = dup_keys + [CONFIG_KEY_COLUMN]
        n_dup = int(df.duplicated(subset=dup_keys).sum())
        if n_dup:
            warnings.append(f"{n_dup} duplicate {tuple(dup_keys)} row(s)")

    # 4. Negative volatilities.
    neg_cols = [c for c in present_est if bool((df[c] < 0).any())]
    if neg_cols:
        warnings.append(f"negative volatility values in column(s): {neg_cols}")

    # 5. Per-ticker date monotonicity (in the given row order).
    if not missing_keys:
        dates = pd.to_datetime(df["date"], errors="coerce")
        non_monotone = [
            str(ticker)
            for ticker, grp in dates.groupby(df["ticker"])
            if not grp.dropna().is_monotonic_increasing
        ]
        if non_monotone:
            warnings.append(
                f"dates not monotonically increasing within ticker(s): {non_monotone}"
            )

    # 6. config_key isolation: mixing configs in one frame is a contract risk.
    if CONFIG_KEY_COLUMN in df.columns:
        distinct = df[CONFIG_KEY_COLUMN].dropna().unique()
        if len(distinct) > 1:
            warnings.append(
                f"{len(distinct)} distinct config_key values present; derived "
                "features must be computed within a single config_key"
            )

    # 7. Scale heuristic: annualized vols should be decimals, not percentages.
    over_ceiling = [
        c for c in present_est if bool((df[c].abs() > _DECIMAL_VOL_SANITY_CEILING).any())
    ]
    if over_ceiling:
        warnings.append(
            f"values exceed {_DECIMAL_VOL_SANITY_CEILING:g} in column(s) {over_ceiling}; "
            "expected decimals (0.09 == 9%), not percentages"
        )

    return warnings


def normalize_volatility_surface(surface_df: pd.DataFrame) -> pd.DataFrame:
    """Return a stable, canonically-ordered, single-``config_key`` surface frame.

    Coerces ``date`` to tz-naive ``datetime64``, orders columns as
    ``date, ticker, <estimators present>, <comparison features present>,
    config_key, <extras>``, and sorts by ``(ticker, date)``. Warm-up ``NaN`` rows
    are preserved (never dropped) so they serialise to ``null`` downstream.

    Raises ``ValueError`` if the key columns are absent or if the frame mixes
    more than one ``config_key`` — the latter would silently corrupt every
    point-in-time percentile/ratio computed downstream (spec §4.3).
    """
    if surface_df is None:
        raise ValueError("surface_df is None")

    missing_keys = [c for c in SURFACE_KEY_COLUMNS if c not in surface_df.columns]
    if missing_keys:
        raise ValueError(f"surface is missing key column(s): {missing_keys}")

    df = surface_df.copy()

    if CONFIG_KEY_COLUMN in df.columns:
        distinct = df[CONFIG_KEY_COLUMN].dropna().unique()
        if len(distinct) > 1:
            raise ValueError(
                "normalize_volatility_surface requires a single config_key; got "
                f"{len(distinct)}. Filter the surface to one config_key first."
            )

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.tz_localize(None)

    ordered: list[str] = list(SURFACE_KEY_COLUMNS)
    ordered += [c for c in VOL_ESTIMATOR_NAMES if c in df.columns]
    ordered += [c for c in COMPARISON_FEATURE_COLUMNS if c in df.columns]
    if CONFIG_KEY_COLUMN in df.columns:
        ordered.append(CONFIG_KEY_COLUMN)
    ordered += [c for c in df.columns if c not in ordered]

    return df[ordered].sort_values(["ticker", "date"]).reset_index(drop=True)


def surface_data_version(surface_df: pd.DataFrame) -> tuple[str, int]:
    """Return the cache freshness token ``(str(max_date), row_count)`` (spec §7).

    Callers slice the surface to a single ``(config_key, ticker)`` first; the
    token then changes whenever a new row is persisted or the latest date
    advances, so a stale derived result cannot survive a surface update even
    before the TTL expires. Mirrors the shape ``feature_surface._build_cache_key``
    already uses (``str(max date)``, ``len``).
    """
    if surface_df is None or surface_df.empty or "date" not in surface_df.columns:
        return ("", 0)

    max_date = pd.to_datetime(surface_df["date"], errors="coerce").max()
    return (str(max_date), int(len(surface_df)))
