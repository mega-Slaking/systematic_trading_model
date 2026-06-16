"""Macro schemas (spec endpoints 10 + 11, Page 6).

Endpoint 10 returns one series per requested macro indicator (each on its own
date axis -- macro is monthly and sparse, so series are NaN-dropped, §2.6). The
set spans both raw ``macro_data`` columns and derived features (CPI YoY, real
policy rate, yield-curve changes, ...); each series' ``meta`` carries its true
``source``/``unit``/``frequency`` (and ``neutral``/``note`` where relevant) so
the client labels and formats it correctly -- see ``api/services/macro.py`` for
the ``meta.unit`` vocabulary. Endpoint 11 returns the 10Y/2Y yields + their
spread for the yield-curve chart.
"""

from __future__ import annotations

from pydantic import BaseModel

from api.schemas.common import CategoricalSeries, NamedSeries, TableModel


class MacroResponse(BaseModel):
    """One :class:`NamedSeries` per requested indicator (name = indicator key)."""

    series: list[NamedSeries]


class YieldCurveResponse(BaseModel):
    """10Y/2Y yields, the 10Y-2Y spread, and curve-regime interpretation (Phase 2).

    ``spread`` carries ``meta={'fill':'tozeroy'}``. ``curve_regime`` is the
    bull/bear steepening/flattening classification over time (categorical);
    ``inverted_intervals`` are the ``[{start, end}]`` spans where the spread is
    inverted (for shading); ``current_regime`` is the latest classified label.
    """

    gs10: NamedSeries
    gs2: NamedSeries
    spread: NamedSeries
    curve_regime: CategoricalSeries
    inverted_intervals: list[dict]
    current_regime: str | None


class MacroSnapshotCard(BaseModel):
    """The latest reading of one indicator (spec Page 6 snapshot cards).

    Each card carries its **own** ``observation_date`` -- a monthly series must
    never be shown as if it shared a daily series' date. ``value`` is a number for
    numeric indicators or a label string for categorical ones (e.g. the curve
    regime). ``change_3m`` / ``direction`` summarise 3-month momentum.
    """

    key: str
    label: str
    value: float | str | None
    unit: str | None  # "pct" | "pct_frac" | "pp" | "level" | None (see services/macro.py)
    observation_date: str | None
    change_3m: float | None
    direction: str | None  # "up" | "down" | "flat" | None (categorical)
    is_stale: bool


class MacroSnapshotResponse(BaseModel):
    """Latest-reading snapshot cards + the newest macro date they're measured against."""

    cards: list[MacroSnapshotCard]
    as_of: str


class RegimeTimelineResponse(BaseModel):
    """Macro-regime timeline for shading an ETF chart (spec Phase 4).

    ``regime`` is the dashboard's transparent rule-based classification over time
    (categorical). ``engine_regime`` is an optional comparison overlay from the
    engine's persisted ``macro_supports_duration`` signal (decision #6: surface
    both; ``None`` if no backtest regime trace exists). ``legend`` maps each
    dashboard regime to its economic-prior bond preference (a prior, not a fitted
    result). The dashboard regimes are explanatory and must NOT be read as the
    engine's allocation regimes.
    """

    regime: CategoricalSeries
    engine_regime: CategoricalSeries | None
    legend: dict[str, str]


class ConditionalReturnsResponse(BaseModel):
    """How TLT/AGG/SHY behaved *after* each macro regime (spec Phase 5).

    A regime × ETF :class:`TableModel` of forward-return statistics. This is
    **descriptive, not predictive**: ``is_lagged`` records that macro is lagged to
    an availability proxy (no look-ahead); ``point_in_time_release_available`` is
    ``False`` (FRED gives reference months, not release dates); and ``notes``
    carries the overlapping-horizon / small-sample caveats the UI must surface.
    Forward returns are decimal fractions; a ``thin`` row flag marks regimes with
    fewer than the requested minimum observations.
    """

    table: TableModel
    is_lagged: bool
    point_in_time_release_available: bool
    notes: list[str]


class ScatterPoint(BaseModel):
    """One month: a macro reading (``x``) vs the ETF's subsequent return (``y``)."""

    date: str
    x: float
    y: float


class ForwardReturnScatterResponse(BaseModel):
    """Δ-macro vs subsequent-ETF-return scatter (spec §18 explorer display mode).

    Each point pairs a macro indicator's value at month ``date`` with the ETF's
    forward total return over ``horizon``, measured only *after* the reading was
    knowable (lagged, no look-ahead). Descriptive — association is not causation,
    and overlapping windows make the points non-independent (see ``note``).
    """

    points: list[ScatterPoint]
    etf: str
    horizon: str
    x_key: str
    x_label: str
    x_unit: str | None
    n: int
    note: str
