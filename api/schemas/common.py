"""Core shared schemas (spec §4.2).

The figure-to-payload strategy hinges on two primitives: a chart trace is just
*(name, x[], y[])*, so we ship exactly that and let the React side draw it. All
floats are nullable because the serialization boundary maps ``NaN``/``Inf`` to
``null`` (spec §6) -- React renders ``null`` as a gap in the line.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SeriesPoint(BaseModel):
    """A single (x, y) point. ``value`` is ``None`` for NaN/Inf (§6)."""

    date: str  # "YYYY-MM-DD"
    value: float | None


class NamedSeries(BaseModel):
    """A named chart trace: a legend label plus its (x, y) points."""

    name: str  # trace/legend label, e.g. "B&H: TLT" or "rolling_sharpe"
    points: list[SeriesPoint]  # the (x, y) the chart library plots
    meta: dict | None = None  # optional style hints, units, axis id, ...


class TableModel(BaseModel):
    """A generic table: column order plus list-of-records rows (values JSON scalars or null)."""

    columns: list[str]
    rows: list[dict]


class ErrorResponse(BaseModel):
    """The consistent error envelope (spec §4.1)."""

    detail: str
    code: str | None = Field(
        default=None,
        description="Machine-readable code, e.g. SCENARIO_NOT_FOUND.",
    )
