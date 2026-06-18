"""Phase 3 — unified volatility-state classifier (instantaneous **and** confirmed).

Collapses Phase 1 level + Phase 2 direction/ratio into one concise, deterministic,
explainable **diagnostic state**, via an ordered precedence model. Two series are
produced: an *instantaneous* state (direct rule output) and a *confirmed* state
that only changes after a new state has persisted for ``confirmation_days``
consecutive trading days. The headline card and the all-asset table use the
**confirmed** state; this removes the single-day ``Extreme`` / threshold-crossing
flicker from the headline.

A diagnostic state is **not** a validated trading signal (that is Phase 9), and
nothing here changes any strategy weight. All logic is pure and lives in
``src/volatility/`` (no API/React coupling).

Precedence (first match wins), with
``expansion_score = (direction=="Rising") + (term_state=="Expansion")`` and
``contraction_score = (direction=="Falling") + (term_state=="Contraction")``:

1. percentile / direction / term_ratio unavailable        -> Unknown
2. Extreme level                                           -> Shock
3. Elevated|High and expansion_score == 2                  -> Stress Expansion
4. Elevated|High and contraction_score == 2                -> Normalisation
5. Elevated|High otherwise                                 -> Persistent Stress
6. Low|Normal and expansion_score >= 1                     -> Early Expansion
7. Low|Normal otherwise                                    -> Calm
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pandas as pd

from src.volatility.direction import classify_volatility_term_state
from src.volatility.percentiles import classify_volatility_level

UNKNOWN_STATE = "Unknown"


@dataclass(frozen=True)
class VolatilityStateConfig:
    """Thresholds + confirmation policy for the unified state (all configurable)."""

    low_percentile: float = 0.20
    normal_percentile: float = 0.60
    elevated_percentile: float = 0.80
    high_percentile: float = 0.95
    expansion_ratio: float = 1.15
    contraction_ratio: float = 0.85
    rising_change: float = 0.10
    falling_change: float = -0.10
    # Trading days a new state must persist before the confirmed state flips. Tuned
    # to 10 (~2 weeks) so the confirmed regime changes ~6x/year rather than ~14x at
    # 3 days — a regime cadence for the shading/markers, not a per-wiggle signal. The
    # card still surfaces the un-debounced instantaneous state alongside.
    confirmation_days: int = 10

    def level_thresholds(self) -> dict[str, float]:
        """The percentile band edges, in the shape ``classify_volatility_level`` expects."""
        return {
            "low": self.low_percentile,
            "normal": self.normal_percentile,
            "elevated": self.elevated_percentile,
            "high": self.high_percentile,
        }

    def version(self) -> str:
        """Stable 12-char hash of the fields for cache keys (§7.2).

        Uses ``hashlib`` (not the builtin ``hash``, which is per-process salted) so
        the version is reproducible across processes — a threshold change forces a
        new cache key.
        """
        fields = (
            self.low_percentile, self.normal_percentile, self.elevated_percentile,
            self.high_percentile, self.expansion_ratio, self.contraction_ratio,
            self.rising_change, self.falling_change, self.confirmation_days,
        )
        return hashlib.sha1(repr(fields).encode()).hexdigest()[:12]


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def classify_volatility_state(
    percentile: float | None,
    direction: str,
    term_ratio: float | None,
    config: VolatilityStateConfig,
) -> str:
    """Instantaneous diagnostic state via the ordered precedence rules (see module docstring)."""
    # Rule 1: any required input unavailable.
    if _is_missing(percentile) or direction == UNKNOWN_STATE or _is_missing(term_ratio):
        return UNKNOWN_STATE

    level = classify_volatility_level(percentile, config.level_thresholds())
    term_state = classify_volatility_term_state(
        term_ratio, config.expansion_ratio, config.contraction_ratio
    )
    expansion_score = int(direction == "Rising") + int(term_state == "Expansion")
    contraction_score = int(direction == "Falling") + int(term_state == "Contraction")

    # Rule 2: Extreme dominates.
    if level == "Extreme":
        return "Shock"

    # Rules 3–5: stressed levels.
    if level in ("Elevated", "High"):
        if expansion_score == 2:
            return "Stress Expansion"
        if contraction_score == 2:
            return "Normalisation"
        return "Persistent Stress"

    # Rules 6–7: calm levels.
    if expansion_score >= 1:
        return "Early Expansion"
    return "Calm"


def compute_confirmed_state_series(
    instantaneous_state: pd.Series,
    confirmation_days: int = 3,
) -> pd.Series:
    """Persistence-debounced confirmed state.

    The confirmed state adopts a new instantaneous state only once it has persisted
    unchanged for ``confirmation_days`` consecutive observations; until then it holds
    the previous confirmed value (seeded to ``Unknown``). With
    ``confirmation_days <= 1`` the confirmed series equals the instantaneous series.
    """
    confirmed = UNKNOWN_STATE
    run_value: object = None
    run_len = 0
    out: list[str] = []

    for state in instantaneous_state:
        if state == run_value:
            run_len += 1
        else:
            run_value = state
            run_len = 1
        if run_len >= confirmation_days:
            confirmed = state
        out.append(confirmed)

    return pd.Series(out, index=instantaneous_state.index, dtype=object)


def explain_volatility_state(row: pd.Series) -> str:
    """Deterministic, template-based one-line explanation from the visible inputs.

    Reads ``volatility_level``, ``percentile_ordinal``, ``direction``,
    ``term_state`` and ``term_ratio`` off the row. No external model; identical
    inputs always yield an identical string.
    """
    state = row.get("confirmed_state", row.get("state"))
    level = row.get("volatility_level")
    if state in (None, UNKNOWN_STATE) or level in (None, "Insufficient history") or _is_missing(level):
        return "Insufficient history to classify the volatility state."

    ordinal = row.get("percentile_ordinal")
    direction = row.get("direction", UNKNOWN_STATE)
    term_state = row.get("term_state", UNKNOWN_STATE)
    term_ratio = row.get("term_ratio")

    direction_phrase = {
        "Rising": "and rising",
        "Falling": "and falling",
        "Stable": "and holding steady",
    }.get(direction, "")
    term_phrase = {
        "Expansion": "pulling above",
        "Contraction": "pulling below",
        "Balanced": "in line with",
    }.get(term_state, "relative to")
    ordinal_txt = f"~{int(ordinal)}th percentile" if ordinal is not None and not _is_missing(ordinal) else "percentile n/a"
    ratio_txt = f"{float(term_ratio):.2f}" if not _is_missing(term_ratio) else "n/a"

    parts = [f"{level} volatility ({ordinal_txt})"]
    if direction_phrase:
        parts.append(direction_phrase)
    sentence = " ".join(parts)
    return (
        f"{sentence}; short-term volatility is {term_phrase} its 60-day baseline "
        f"(20D/60D {ratio_txt})."
    )


def compute_state_series(
    features_df: pd.DataFrame,
    config: VolatilityStateConfig,
) -> tuple[pd.Series, pd.Series]:
    """For one ticker's per-row features, return ``(instantaneous, confirmed)`` state series.

    ``features_df`` must be a single ticker's rows carrying ``percentile``,
    ``direction`` and ``term_ratio`` (the state inputs). The caller is responsible
    for sorting by date; both returned series share ``features_df``'s index.
    """
    instantaneous = pd.Series(
        [
            classify_volatility_state(p, d, r, config)
            for p, d, r in zip(features_df["percentile"], features_df["direction"], features_df["term_ratio"])
        ],
        index=features_df.index,
        dtype=object,
    )
    confirmed = compute_confirmed_state_series(instantaneous, config.confirmation_days)
    return instantaneous, confirmed


def build_latest_volatility_state_table(
    features_df: pd.DataFrame,
    as_of_date: pd.Timestamp,
    config: VolatilityStateConfig,
) -> pd.DataFrame:
    """Per-asset confirmed state + supporting features at (or before) ``as_of_date``.

    ``features_df`` carries point-in-time per-``(date, ticker)`` columns:
    ``percentile``, ``direction``, ``term_ratio`` (state inputs) plus the display
    columns ``current_volatility``, ``percentile_ordinal``, ``volatility_level``,
    ``change_20d``, ``term_state``. For each ticker this computes the instantaneous
    state per row, debounces it into a confirmed state, and returns the latest row
    on/before ``as_of_date`` with ``instantaneous_state``, ``confirmed_state`` and a
    deterministic ``state_explanation`` attached.
    """
    if features_df.empty:
        return pd.DataFrame()

    as_of = pd.to_datetime(as_of_date)
    out_rows: list[pd.Series] = []

    for _, grp in features_df.groupby("ticker", sort=True):
        g = grp.sort_values("date").reset_index(drop=True)
        instantaneous, confirmed = compute_state_series(g, config)
        g = g.assign(instantaneous_state=instantaneous.to_numpy(), confirmed_state=confirmed.to_numpy())

        eligible = g[g["date"] <= as_of]
        if eligible.empty:
            continue
        row = eligible.iloc[-1].copy()
        row["state_explanation"] = explain_volatility_state(row)
        out_rows.append(row)

    return pd.DataFrame(out_rows).reset_index(drop=True)
