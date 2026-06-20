"""Phase 6 — confirmed-state ranges (shading) and debounced transitions (markers).

Both operate on the **already-confirmed** Phase 3 state series (so they are
persistence-debounced by construction — Phase 6 does not re-introduce basic
confirmation). ``build_state_ranges`` collapses the series into contiguous
``(start, end, state)`` bands for chart shading; ``detect_persistent_state_transitions``
emits one marker per confirmed-state change, suppressing same-kind repeats inside
a ``cooldown_days`` window so the chart is not noisy.

No figure is built here — these return tidy frames; React assembles the Plotly
traces/shapes (§ no server-side ``go.Figure``).
"""

from __future__ import annotations

import pandas as pd


def _slug(state: str) -> str:
    return state.lower().replace(" ", "_")


def build_state_ranges(confirmed_state_series: pd.Series) -> pd.DataFrame:
    """Collapse a date-indexed confirmed-state series into contiguous ranges.

    Returns ``DataFrame[start, end, state]`` with one row per maximal run of an
    unchanged state. Ranges are contiguous and non-overlapping; ``start``/``end``
    are the first/last dates of each run. Empty input -> empty frame.
    """
    s = confirmed_state_series.dropna()
    if s.empty:
        return pd.DataFrame(columns=["start", "end", "state"])

    dates = pd.to_datetime(pd.Series(s.index))
    states = s.to_numpy()
    # A new run starts wherever the state differs from the previous row.
    change = [True] + [states[i] != states[i - 1] for i in range(1, len(states))]
    run_ids = pd.Series(change).cumsum().to_numpy()

    rows = []
    for run_id in pd.unique(run_ids):
        mask = run_ids == run_id
        run_dates = dates[mask]
        rows.append(
            {
                "start": run_dates.iloc[0],
                "end": run_dates.iloc[-1],
                "state": states[mask][0],
            }
        )
    return pd.DataFrame(rows, columns=["start", "end", "state"])


def detect_persistent_state_transitions(
    confirmed_state_series: pd.Series,
    confirmation_days: int = 3,
    cooldown_days: int = 10,
) -> pd.DataFrame:
    """Confirmed, cooldown-gated state transitions.

    The input is the **confirmed** (already debounced) state series, so every
    value change is a persistent regime change. One transition is emitted per
    change as ``(date, kind, from_state, to_state, label)`` with
    ``kind = "entered_<to_state_slug>"``. A transition is suppressed if another of
    the **same kind** occurred within the previous ``cooldown_days`` observations,
    keeping the markers sparse. ``confirmation_days`` is accepted for interface
    symmetry; confirmation has already been applied upstream (Phase 3).
    """
    s = confirmed_state_series.dropna()
    if s.empty:
        return pd.DataFrame(columns=["date", "kind", "from_state", "to_state", "label"])

    dates = pd.to_datetime(pd.Series(s.index)).to_numpy()
    states = s.to_numpy()

    rows = []
    last_pos_by_kind: dict[str, int] = {}
    for i in range(1, len(states)):
        if states[i] == states[i - 1]:
            continue
        to_state = states[i]
        kind = f"entered_{_slug(str(to_state))}"
        last = last_pos_by_kind.get(kind)
        if last is not None and (i - last) < cooldown_days:
            continue  # too soon after the previous marker of this kind
        last_pos_by_kind[kind] = i
        rows.append(
            {
                "date": dates[i],
                "kind": kind,
                "from_state": states[i - 1],
                "to_state": to_state,
                "label": f"Entered {to_state}",
            }
        )
    return pd.DataFrame(rows, columns=["date", "kind", "from_state", "to_state", "label"])
