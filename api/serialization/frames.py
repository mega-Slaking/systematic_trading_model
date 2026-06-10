"""The serialization boundary helpers (spec §6, §10.3).

This module is the single home for the three classic JSON hazards:

1. **NaN / Inf -> null.** JSON has no ``NaN``; ``json.dumps(float("nan"))`` emits
   an invalid ``NaN`` token that breaks strict parsers. ``tearsheet_calculator``
   returns ``np.nan`` liberally (undefined ratios, the first ~252 rolling rows,
   empty tails). ``nan_to_none`` maps every non-finite float to ``None`` at the
   boundary; ``sanitize_obj`` recurses that over nested containers. This is the
   single most likely correctness bug in the whole migration (spec §10.3), so it
   is centralized here and round-tripped in ``api/tests/test_serialization.py``
   from the very first endpoint. (Mirrors ``db_writer.py:_none_if_nan``.)

2. **Dates -> ISO ``YYYY-MM-DD``.** The DB is genuinely inconsistent: some tables
   store a ``00:00:00`` time component, others store a plain date string
   (spec §6). ``to_iso`` normalizes everything; never hand a raw DB date to the
   client.

3. **Float precision.** We do not pre-round (full float64 is kept; React formats
   for display) except where a caller opts into rounding for wire size.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from api.schemas.common import NamedSeries, SeriesPoint, TableModel


def nan_to_none(value: Any) -> Any:
    """Map non-finite floats (NaN / +-Inf) and pandas-NA to ``None``; pass everything else through.

    Handles Python ``float``, numpy floating scalars (which are ``float``
    instances under numpy 2.x for ``float64`` via ``isinstance`` checks below),
    and pandas missing sentinels. Non-float values are returned unchanged so the
    function is safe to apply blanket-wise to mixed records.
    """
    # Fast path for the common JSON scalars that are never "missing".
    if value is None or isinstance(value, (bool, int, str)):
        return value

    # pandas NA / NaT and numpy NaN all answer True here; guard with a try because
    # ``pd.isna`` raises on array-likes (which should never reach a scalar helper).
    try:
        is_missing = bool(pd.isna(value))
    except (TypeError, ValueError):
        is_missing = False
    if is_missing:
        return None

    # Catch +-Inf (which is not "missing" but is still invalid JSON).
    if isinstance(value, float) and not math.isfinite(value):
        return None
    # numpy floats are not always ``float`` subclasses depending on platform; coerce.
    try:
        as_float = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return value
    if isinstance(value, (int,)):  # already handled, but keep ints as-is
        return value
    if not math.isfinite(as_float):
        return None
    return value


def sanitize_obj(obj: Any) -> Any:
    """Recursively apply :func:`nan_to_none` through dicts / lists / tuples.

    Used for table rows and dataclass-derived dicts so a nested ``NaN`` can never
    slip past the boundary as an invalid JSON token.
    """
    if isinstance(obj, dict):
        return {k: sanitize_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_obj(v) for v in obj]
    return nan_to_none(obj)


def to_iso(series: pd.Series) -> pd.Series:
    """Normalize a date-like Series to ISO ``YYYY-MM-DD`` strings (drops any time component).

    Accepts pandas ``Timestamp``/``datetime64`` series or object/string series
    (some DB columns store ``"2010-01-05 00:00:00"``, others ``"2010-01-05"``).
    Coerces via ``pd.to_datetime`` then formats; unparseable values become ``None``.

    ``format="mixed"`` is required: without it, pandas 2.x infers a single format
    from the first element, so an object column that mixes ``"...-01 00:00:00"``
    with ``"...-02"`` would silently turn the bare-date rows into ``NaT`` -- the
    exact heterogeneous-date hazard §6 warns about. ``format="mixed"`` parses each
    element independently. It is a no-op for an already-``datetime64`` series.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        dt = series
    else:
        dt = pd.to_datetime(series, errors="coerce", format="mixed")
    # ``strftime`` on NaT yields the string "NaT"; replace those with None instead.
    out = dt.dt.strftime("%Y-%m-%d")
    return out.where(dt.notna(), None)


def series_to_points(
    frame: pd.DataFrame,
    *,
    x: str = "date",
    y: str,
    round_to: int | None = None,
) -> list[SeriesPoint]:
    """Build a list of :class:`SeriesPoint` from two columns of ``frame``.

    ``x`` is normalized via :func:`to_iso`; ``y`` is NaN/Inf-sanitized via
    :func:`nan_to_none`. ``round_to`` optionally rounds finite values (used for
    the dense returns scatter to trim wire size, spec §6).
    """
    dates = to_iso(frame[x]).tolist()
    raw_values = frame[y].tolist()
    points: list[SeriesPoint] = []
    for d, v in zip(dates, raw_values):
        clean = nan_to_none(v)
        if round_to is not None and isinstance(clean, float):
            clean = round(clean, round_to)
        points.append(SeriesPoint(date=d, value=clean))
    return points


def df_to_series(
    frame: pd.DataFrame,
    *,
    name: str,
    x: str = "date",
    y: str,
    meta: dict | None = None,
    round_to: int | None = None,
) -> NamedSeries:
    """Convert two columns of ``frame`` into a :class:`NamedSeries` (a chart trace)."""
    return NamedSeries(
        name=name,
        points=series_to_points(frame, x=x, y=y, round_to=round_to),
        meta=meta,
    )


def df_to_table(frame: pd.DataFrame, *, date_columns: tuple[str, ...] = ("date",)) -> TableModel:
    """Convert a DataFrame to a generic :class:`TableModel` (``{columns, rows}``).

    Any column named in ``date_columns`` (and present) is ISO-normalized; all
    cells pass through the NaN/Inf -> null sanitizer. Column order is preserved.
    """
    df = frame.copy()
    for col in date_columns:
        if col in df.columns:
            df[col] = to_iso(df[col])
    # ``where(notna, None)`` turns NaN/NaT into None at the cell level; sanitize_obj
    # then mops up any residual non-finite floats (e.g. +-Inf) per record.
    records = df.where(pd.notna(df), None).to_dict("records")
    rows = [sanitize_obj(rec) for rec in records]
    return TableModel(columns=list(df.columns), rows=rows)
