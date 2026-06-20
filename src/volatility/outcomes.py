"""Phase 9 — historical signal outcome analysis.

Tests, rather than assumes, whether a diagnostic state carried information: for
each horizon it measures the **forward** asset returns and forward-window
drawdowns that *followed* every occurrence of a state, aggregates them by state
with **non-overlapping sampling by default**, and applies **hard
minimum-sample gates**. This is the only phase that may move a diagnostic state
toward a "validated signal", and even then only with explicit sample caveats —
nothing here changes any strategy weight.

Look-ahead alignment (strict, §4.2 / §Phase 9):

* ``state(t)`` comes from the **already one-day-lagged** surface (so it is as-of
  ``t``, information through ``t-1``) — signal features are untouched here, and
  in particular this module **never re-shifts** them.
* ``forward_return(t -> t+h)`` comes from **UNLAGGED** adjusted prices strictly
  **after** ``t``: ``price[t+h] / price[t] - 1``. The state date and the forward
  prices use opposite conventions on purpose; they are never mixed.

Because daily forward windows of length ``h`` overlap heavily, treating every
signal day as an independent observation overstates the evidence. The default
sampler therefore selects a maximal set of **non-overlapping** windows; "all
observations" remains available as an explicit, clearly-labelled override.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Forward horizons in *trading observations* (rows of the price series), label ->
# length. 12M (252) is deliberately omitted — it is an optional later addition.
FORWARD_HORIZONS: dict[str, int] = {"1M": 21, "3M": 63, "6M": 126}

# Diagnostic states analysed by default (matches the Phase 3 precedence outputs).
# "Unknown" is intentionally excluded — it is the absence of a state, not a state.
OUTCOME_STATES: tuple[str, ...] = (
    "Calm",
    "Early Expansion",
    "Stress Expansion",
    "Persistent Stress",
    "Normalisation",
    "Shock",
)

# Mandatory minimum-sample gates on the **effective independent** observation
# count N (cutoffs configurable but deterministic). Each maps to the smallest N
# at which the behaviour applies:
#   N < anecdotal              -> Insufficient sample (no aggregate stats)
#   anecdotal <= N < low       -> Anecdotal      (count / median / min / max only)
#   low <= N < full            -> Low sample     (descriptive stats)
#   N >= full                  -> (none)         (full summary)
DEFAULT_MIN_SAMPLE_GATES: dict[str, int] = {"anecdotal": 5, "low": 10, "full": 20}

# Sample-quality labels keyed by gate tier.
SAMPLE_QUALITY_INSUFFICIENT = "Insufficient sample"
SAMPLE_QUALITY_ANECDOTAL = "Anecdotal"
SAMPLE_QUALITY_LOW = "Low sample"
SAMPLE_QUALITY_FULL = ""  # adequate sample -> no caveat label


def compute_forward_asset_returns(
    prices: pd.Series,
    horizons: dict[str, int] = FORWARD_HORIZONS,
) -> pd.DataFrame:
    """Forward returns from **UNLAGGED** prices strictly **after** each date.

    For each horizon ``h`` (label ``k``) column ``forward_return_{k}`` is
    ``prices.shift(-h) / prices - 1`` — i.e. ``price[t+h] / price[t] - 1``, the
    return realised over the ``h`` observations *after* ``t``. Because it reads
    only future prices it is **never** a signal feature and is never lagged: the
    state side of the join supplies the (already-lagged) information-through-``t-1``
    convention, and the two are kept strictly separate (§Phase 9 alignment).

    The final ``h`` rows have no full forward window and yield ``NaN`` (-> null).
    Division by a zero base price yields ``NaN`` rather than ``inf``.
    """
    prices = prices.astype(float)
    out: dict[str, pd.Series] = {}
    for key, h in horizons.items():
        forward = prices.shift(-h) / prices - 1.0
        out[f"forward_return_{key}"] = forward.replace([np.inf, -np.inf], np.nan)
    return pd.DataFrame(out, index=prices.index)


def compute_forward_window_drawdowns(
    prices: pd.Series,
    horizons: dict[str, int] = FORWARD_HORIZONS,
) -> pd.DataFrame:
    """Worst drawdown inside each forward window (UNLAGGED prices, after ``t``).

    For each horizon ``h`` (label ``k``) column ``forward_max_drawdown_{k}`` is the
    most negative peak-to-trough return reached at any point **within** the window
    ``(t, t+h]`` — i.e. ``min_j (price[t+j] / running_peak - 1)`` for
    ``j = 1..h``, anchored at ``price[t]``. The result is ``<= 0`` (``0.0`` if the
    price only rose); a window that runs off the end of the series (fewer than
    ``h`` future observations) is ``NaN``.

    Like :func:`compute_forward_asset_returns` this reads only prices strictly
    after ``t`` and is never used as a signal feature.
    """
    prices = prices.astype(float)
    values = prices.to_numpy(dtype=float)
    n = len(values)
    out: dict[str, list[float]] = {}

    for key, h in horizons.items():
        col: list[float] = []
        for i in range(n):
            base = values[i]
            end = i + h
            # Need a full window of `h` future observations and a valid, non-zero base.
            if end >= n or not np.isfinite(base) or base == 0.0:
                col.append(np.nan)
                continue
            window = values[i + 1 : end + 1]
            if not np.isfinite(window).all():
                col.append(np.nan)
                continue
            # Running peak anchored at the base price; worst (most negative) drawdown.
            path = np.concatenate(([base], window))
            running_peak = np.maximum.accumulate(path)
            drawdowns = path / running_peak - 1.0
            col.append(float(drawdowns.min()))
        out[f"forward_max_drawdown_{key}"] = col

    return pd.DataFrame(out, index=prices.index)


def select_non_overlapping_dates(signal_dates: pd.Series, horizon_days: int) -> pd.Series:
    """Deterministic non-overlapping selection of signal dates (§Phase 9 algorithm).

    1. Sort the eligible signal dates ascending.
    2. Pick the first eligible date; record it.
    3. Exclude every later candidate whose length-``horizon_days`` forward window
       overlaps the recorded one — i.e. any candidate strictly **before** the
       recorded date's window end. A candidate exactly ``horizon_days`` business
       days later is the next non-overlapping pick (its window starts where the
       previous one ends, so the realised returns share no future bar).
    4. Repeat from the next non-excluded candidate until none remain.

    Overlap is judged on the **date values themselves**: the forward window of a
    recorded date ``d`` is ``[d, d + horizon_days business days)``, so a later
    candidate ``c`` overlaps iff ``c < d + horizon_days`` business days. Business
    days (``pd.offsets.BDay``) match the trading-observation cadence of the
    surface; the input need not be evenly spaced (sparse same-state dates are
    handled correctly). The returned Series preserves the input dtype and
    ascending order. ``horizon_days <= 0`` keeps every unique date (no overlap
    constraint).
    """
    ordered = pd.Series(signal_dates).dropna().drop_duplicates().sort_values().reset_index(drop=True)
    if ordered.empty or horizon_days <= 0:
        return ordered

    bday = pd.offsets.BusinessDay(horizon_days)
    selected: list[int] = []
    window_end = None  # the recorded date's window end; candidates before it overlap
    for position, date in enumerate(ordered):
        if window_end is None or date >= window_end:
            selected.append(position)
            window_end = pd.Timestamp(date) + bday

    return ordered.iloc[selected].reset_index(drop=True)


def classify_sample_quality(
    effective_observations: int,
    gates: dict[str, int] = DEFAULT_MIN_SAMPLE_GATES,
) -> str:
    """Map an effective independent count to its sample-quality label (deterministic).

    ``N < gates['anecdotal']`` -> Insufficient sample; ``[anecdotal, low)`` ->
    Anecdotal; ``[low, full)`` -> Low sample; ``>= full`` -> "" (adequate).
    """
    n = int(effective_observations)
    if n < gates["anecdotal"]:
        return SAMPLE_QUALITY_INSUFFICIENT
    if n < gates["low"]:
        return SAMPLE_QUALITY_ANECDOTAL
    if n < gates["full"]:
        return SAMPLE_QUALITY_LOW
    return SAMPLE_QUALITY_FULL


def _aggregate_window(
    returns: pd.Series,
    drawdowns: pd.Series,
    sample_quality: str,
) -> dict[str, float | None]:
    """Aggregate one state's forward returns/drawdowns under its gate tier.

    The gate tier controls which statistics survive: ``Insufficient sample`` emits
    nothing; ``Anecdotal`` emits median / worst / best only; ``Low sample`` and
    above emit the full descriptive set. Gated-out statistics are ``None`` so they
    serialise to ``null`` at the API boundary.
    """
    blank: dict[str, float | None] = {
        "mean_return": None, "median_return": None, "hit_rate": None,
        "std_return": None, "worst_return": None, "best_return": None,
        "forward_max_drawdown": None,
    }
    if sample_quality == SAMPLE_QUALITY_INSUFFICIENT:
        return blank

    clean = returns.dropna()
    dd_clean = drawdowns.dropna()
    if clean.empty:
        return blank

    # Anecdotal: count / median / min / max only (no mean / hit rate / std).
    median = float(clean.median())
    worst = float(clean.min())
    best = float(clean.max())
    worst_dd = float(dd_clean.min()) if not dd_clean.empty else None
    if sample_quality == SAMPLE_QUALITY_ANECDOTAL:
        return {
            **blank,
            "median_return": median, "worst_return": worst, "best_return": best,
            "forward_max_drawdown": worst_dd,
        }

    # Low sample and above: full descriptive set.
    return {
        "mean_return": float(clean.mean()),
        "median_return": median,
        "hit_rate": float((clean > 0).mean()),
        "std_return": float(clean.std(ddof=1)) if len(clean) >= 2 else None,
        "worst_return": worst,
        "best_return": best,
        "forward_max_drawdown": worst_dd,
    }


def _aggregate_group(
    group_rows: pd.DataFrame,
    horizon_col: str,
    drawdown_col: str,
    label: str,
    non_overlapping: bool,
    horizon_days: int,
    gates: dict[str, int],
) -> dict[str, object]:
    """Aggregate one already-filtered group (state or condition) into an outcome row.

    ``group_rows`` is the merged ``date ⋈ forward`` slice for a single label. With
    ``non_overlapping`` the dates are first thinned to a maximal non-overlapping set
    (window = ``horizon_days``); the **effective independent count** is the thinned
    dates with a defined forward return, which drives the sample-quality gate and
    therefore which statistics survive. An empty group yields a zero-observation
    "Insufficient sample" row, so every requested label stays visible without any
    special-casing. Shared by the state table and the combined-condition table so
    both gate identically.
    """
    rows = group_rows
    if non_overlapping:
        kept_dates = select_non_overlapping_dates(rows["date"], horizon_days)
        rows = rows[rows["date"].isin(kept_dates)]

    returns = rows[horizon_col]
    drawdowns = (
        rows[drawdown_col] if drawdown_col in rows.columns
        else pd.Series(dtype=float, index=rows.index)
    )

    effective = int(returns.notna().sum())
    sample_quality = classify_sample_quality(effective, gates)
    stats = _aggregate_window(returns, drawdowns, sample_quality)
    return {"state": label, "effective_observations": effective,
            "sample_quality": sample_quality, **stats}


def build_volatility_signal_outcome_table(
    features_df: pd.DataFrame,
    forward_returns_df: pd.DataFrame,
    signal_col: str,
    horizon_col: str,
    non_overlapping: bool = True,
    min_sample_gates: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Aggregate forward outcomes by state with sample-quality gating + labels.

    ``features_df`` carries the point-in-time state per ``date`` in ``signal_col``
    (e.g. a confirmed-state series) — the **already-lagged**, as-of-``t`` signal.
    ``forward_returns_df`` carries the **unlagged**, after-``t`` forward returns in
    ``horizon_col`` and (optionally) the matching ``forward_max_drawdown_*`` column;
    both are indexed/keyed by the same ``date`` axis. They are joined on ``date``
    one-to-one — never many-to-many — so no row is duplicated.

    With ``non_overlapping=True`` (the default) the eligible dates for each state
    are thinned to a maximal non-overlapping set via
    :func:`select_non_overlapping_dates` (window length = the horizon implied by
    ``horizon_col``). The **effective independent observation count** is the number
    of dates that survive thinning *and* have a defined forward return.

    Returns one row per state in :data:`OUTCOME_STATES` order (states present in
    the data), with ``effective_observations``, ``sample_quality`` and the gated
    statistics (``None`` where the tier suppresses them).
    """
    gates = min_sample_gates or DEFAULT_MIN_SAMPLE_GATES
    horizon_days = _horizon_length(horizon_col)

    drawdown_col = horizon_col.replace("forward_return_", "forward_max_drawdown_", 1)

    # One-to-one join on date: state (as-of t) ⋈ forward return/drawdown (after t).
    feats = features_df[["date", signal_col]].copy()
    fwd_cols = ["date", horizon_col] + ([drawdown_col] if drawdown_col in forward_returns_df.columns else [])
    fwd = forward_returns_df[fwd_cols].copy()
    # `validate="one_to_one"` makes pandas *raise* on any many-to-many key collision
    # (the no-row-multiplication guard the spec requires).
    merged = feats.merge(fwd, on="date", how="inner", validate="one_to_one")

    states_present = [s for s in OUTCOME_STATES if (merged[signal_col] == s).any()]
    # Preserve any other (non-canonical) states deterministically after the canonical set.
    extras = sorted(
        str(s) for s in merged[signal_col].dropna().unique()
        if s not in OUTCOME_STATES and str(s) != "Unknown"
    )

    rows: list[dict[str, object]] = []
    for state in states_present + extras:
        # Per-group thinning + gating now lives in the shared `_aggregate_group`
        # (also used by the combined-condition table) so both gate identically.
        # --- old inline aggregation (kept commented as a rollback safety net) ---
        # state_rows = merged[merged[signal_col] == state]
        # if non_overlapping:
        #     kept_dates = select_non_overlapping_dates(state_rows["date"], horizon_days)
        #     state_rows = state_rows[state_rows["date"].isin(kept_dates)]
        # returns = state_rows[horizon_col]
        # drawdowns = (
        #     state_rows[drawdown_col] if drawdown_col in state_rows.columns
        #     else pd.Series(dtype=float, index=state_rows.index)
        # )
        # effective = int(returns.notna().sum())
        # sample_quality = classify_sample_quality(effective, gates)
        # stats = _aggregate_window(returns, drawdowns, sample_quality)
        # rows.append({"state": state, "effective_observations": effective,
        #              "sample_quality": sample_quality, **stats})
        state_rows = merged[merged[signal_col] == state]
        rows.append(
            _aggregate_group(state_rows, horizon_col, drawdown_col, state, non_overlapping, horizon_days, gates)
        )

    return pd.DataFrame(rows)


def _horizon_length(horizon_col: str) -> int:
    """Resolve the forward-window length (observations) implied by ``horizon_col``.

    ``horizon_col`` is a ``forward_return_{label}`` column; the label maps back to
    :data:`FORWARD_HORIZONS`. An unknown label is a programming error (the caller
    builds both the column and the table), so it raises rather than silently using
    a wrong overlap window.
    """
    label = horizon_col.replace("forward_return_", "", 1)
    if label not in FORWARD_HORIZONS:
        raise ValueError(f"unknown forward-return column '{horizon_col}' (label '{label}')")
    return FORWARD_HORIZONS[label]


def build_state_return_distribution(
    features_df: pd.DataFrame,
    forward_returns_df: pd.DataFrame,
    signal_col: str,
    horizon_col: str,
    non_overlapping: bool = True,
    states: tuple[str, ...] | list[str] | None = None,
) -> dict[str, list[float]]:
    """Per-state forward-return *samples* (the thinned per-observation distribution).

    Mirrors the one-to-one join and non-overlapping thinning of
    :func:`build_volatility_signal_outcome_table` but returns, for each state, the
    raw per-window forward returns over its (optionally thinned) signal dates —
    the input a box plot needs, rather than aggregate statistics. States are
    returned in :data:`OUTCOME_STATES` order (or the ``states`` order supplied),
    each mapped to the list of *defined* forward returns; ``NaN`` terminal windows
    are dropped so a box reflects only realised outcomes. Look-ahead alignment is
    identical to the aggregate table (state as-of ``t`` ⋈ forward strictly after ``t``).
    """
    horizon_days = _horizon_length(horizon_col)
    merged = features_df[["date", signal_col]].merge(
        forward_returns_df[["date", horizon_col]], on="date", how="inner", validate="one_to_one"
    )
    candidate_states = list(states) if states is not None else list(OUTCOME_STATES)
    present = [s for s in candidate_states if (merged[signal_col] == s).any()]

    result: dict[str, list[float]] = {}
    for state in present:
        state_rows = merged[merged[signal_col] == state]
        if non_overlapping:
            kept_dates = select_non_overlapping_dates(state_rows["date"], horizon_days)
            state_rows = state_rows[state_rows["date"].isin(kept_dates)]
        values = state_rows[horizon_col].dropna()
        result[state] = [float(v) for v in values]
    return result


# --------------------------------------------------------------------------- #
# Combined-condition signals (§Phase 9 — added incrementally on top of states)
# --------------------------------------------------------------------------- #

# Each combined condition is a point-in-time boolean over the **already-lagged**
# feature surface (plus the as-of-(t-1) price return and, optionally, the
# cross-asset relative-vol percentile). They are *not* mutually exclusive — a date
# can satisfy several — so they are analysed one condition at a time rather than as
# a single categorical state column.
COND_VOL_UP_PRICE_DOWN = "Vol rising + price falling"
COND_VOL_UP_PRICE_UP = "Vol rising + price rising"
COND_VOL_DOWN_AFTER_HIGH = "Vol falling after High/Extreme"
COND_RATIO_EXPANSION = "20D/60D in expansion"
COND_AGREEMENT_LOW = "Estimator agreement Low"
COND_RELATIVE_VOL_EXTREME = "TLT/AGG relative vol > 90th pct"

# The single-asset conditions (always computable from one ticker's features). The
# cross-asset condition is appended by the caller only when it supplies the
# TLT/AGG percentile column.
COMBINED_CONDITIONS: tuple[str, ...] = (
    COND_VOL_UP_PRICE_DOWN,
    COND_VOL_UP_PRICE_UP,
    COND_VOL_DOWN_AFTER_HIGH,
    COND_RATIO_EXPANSION,
    COND_AGREEMENT_LOW,
)

# Trailing observations over which a recent High/Extreme level still counts as
# "after High/Extreme" (≈ one trading month), and the cross-asset "extreme"
# relative-vol percentile gate.
RECENT_PEAK_LOOKBACK = 20
RELATIVE_EXTREME_PERCENTILE = 0.90

_HIGH_LEVELS = ("High", "Extreme")


def compute_combined_condition_flags(
    features_df: pd.DataFrame,
    price_threshold: float,
    recent_peak_lookback: int = RECENT_PEAK_LOOKBACK,
    relative_extreme_percentile: float = RELATIVE_EXTREME_PERCENTILE,
) -> pd.DataFrame:
    """Per-date boolean membership for each combined diagnostic condition (point-in-time).

    Every flag is derived purely from the **already-lagged** feature columns
    (``direction``, ``volatility_level``, ``term_state``, ``estimator_agreement``)
    plus the as-of-(t-1) 20-day price return (``asset_return_20d``) and, where the
    caller supplies it, the cross-asset TLT/AGG relative-vol percentile
    (``relative_pair_percentile``). So a flag at ``t`` reads only information
    through ``t-1`` and is **never re-shifted**; the trailing "after High/Extreme"
    peak window is causal (it looks only backward).

    Returns a frame of ``date`` + one boolean column per condition in
    :data:`COMBINED_CONDITIONS` order. The cross-asset column
    (:data:`COND_RELATIVE_VOL_EXTREME`) is included only when
    ``relative_pair_percentile`` is present in ``features_df``. Missing inputs
    (``NaN`` / ``"Unknown"``) deterministically yield ``False`` for that condition.
    """
    df = features_df
    index = df.index
    false = pd.Series(False, index=index)

    def col(name: str) -> pd.Series | None:
        return df[name] if name in df.columns else None

    direction = col("direction")
    rising = (direction == "Rising") if direction is not None else false
    falling = (direction == "Falling") if direction is not None else false

    price_ret = col("asset_return_20d")
    threshold = abs(float(price_threshold))
    price_down = (price_ret <= -threshold) if price_ret is not None else false
    price_up = (price_ret >= threshold) if price_ret is not None else false

    level = col("volatility_level")
    if level is not None:
        is_high = level.isin(_HIGH_LEVELS)
        recent_high = is_high.rolling(max(1, int(recent_peak_lookback)), min_periods=1).max() > 0
    else:
        recent_high = false

    term_state = col("term_state")
    in_expansion = (term_state == "Expansion") if term_state is not None else false

    agreement = col("estimator_agreement")
    agreement_low = (agreement == "Low") if agreement is not None else false

    out: dict[str, object] = {
        "date": df["date"].to_numpy(),
        COND_VOL_UP_PRICE_DOWN: (rising & price_down).fillna(False).to_numpy(),
        COND_VOL_UP_PRICE_UP: (rising & price_up).fillna(False).to_numpy(),
        COND_VOL_DOWN_AFTER_HIGH: (falling & recent_high).fillna(False).to_numpy(),
        COND_RATIO_EXPANSION: in_expansion.fillna(False).to_numpy(),
        COND_AGREEMENT_LOW: agreement_low.fillna(False).to_numpy(),
    }

    rel_pct = col("relative_pair_percentile")
    if rel_pct is not None:
        out[COND_RELATIVE_VOL_EXTREME] = (rel_pct > float(relative_extreme_percentile)).fillna(False).to_numpy()

    return pd.DataFrame(out)


def build_combined_condition_outcome_table(
    conditions_df: pd.DataFrame,
    forward_returns_df: pd.DataFrame,
    horizon_col: str,
    non_overlapping: bool = True,
    min_sample_gates: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Aggregate forward outcomes for each combined-condition column (§Phase 9).

    ``conditions_df`` carries ``date`` + one boolean column per condition (from
    :func:`compute_combined_condition_flags`). For each condition the dates where
    it holds are aggregated through :func:`build_volatility_signal_outcome_table` —
    the *same* one-to-one join, non-overlapping sampler and minimum-sample gates as
    the diagnostic-state table — so conditions and states are gated identically and
    cannot drift apart. A condition that never holds emits a single zero-observation
    ``Insufficient sample`` row, so every defined condition stays visible. The
    returned frame has the same columns as the state table, with the condition
    label in ``state``.
    """
    gates = min_sample_gates or DEFAULT_MIN_SAMPLE_GATES
    horizon_days = _horizon_length(horizon_col)
    drawdown_col = horizon_col.replace("forward_return_", "forward_max_drawdown_", 1)
    condition_cols = [c for c in conditions_df.columns if c != "date"]

    # Join conditions ⋈ forward **once** on date (one_to_one -> raises on any
    # duplicate-date collision, the no-row-multiplication guard). Each condition is
    # then a boolean column over the same merged rows; an empty group falls straight
    # through `_aggregate_group` to a zero-observation "Insufficient sample" row, so
    # every defined condition stays visible without a synthetic single-row frame.
    fwd_cols = ["date", horizon_col] + ([drawdown_col] if drawdown_col in forward_returns_df.columns else [])
    merged = conditions_df.merge(
        forward_returns_df[fwd_cols], on="date", how="inner", validate="one_to_one"
    )

    rows: list[dict[str, object]] = []
    for label in condition_cols:
        group = merged[merged[label].fillna(False).astype(bool)]
        rows.append(
            _aggregate_group(group, horizon_col, drawdown_col, label, non_overlapping, horizon_days, gates)
        )

    if not rows:
        return pd.DataFrame(columns=["state", "effective_observations", "sample_quality"])
    return pd.DataFrame(rows)
