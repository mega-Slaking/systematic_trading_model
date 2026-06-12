"""Dataclass -> JSON-safe helpers (spec §6), incl. the ``TearsheetResult`` walker.

A frozen dataclass of plain scalars (``TearsheetMetrics``) serializes via
``dataclasses.asdict`` + the NaN/Inf sanitizer. ``TearsheetResult`` mixes that
metrics dataclass with DataFrame fields, so ``tearsheet_to_response`` maps each
known field to the right converter: curves -> ``NamedSeries``, the three summary
frames -> ``TableModel`` (or ``null`` when the builder returned an *empty* frame --
the empty-vs-None gotcha, §6), and the metrics -> a flat model.

The engine type is referenced only under ``TYPE_CHECKING`` so this module never
imports ``accounting`` at runtime (the walker reads ``result`` structurally).
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from api.schemas.common import TableModel
from api.schemas.tearsheet import TearsheetMetricsModel, TearsheetResponse
from api.serialization.frames import df_to_series, df_to_table, nan_to_none, sanitize_obj

if TYPE_CHECKING:
    import pandas as pd

    from accounting.tearsheet_models import TearsheetResult

# rolling_metrics is a single DataFrame; split into one NamedSeries per metric
# column. rolling_sharpe is a ratio (the UI puts it on a secondary axis); the
# others are fractions. ``meta.metric`` carries the raw key for that mapping.
_ROLLING_SERIES: tuple[tuple[str, str], ...] = (
    ("rolling_volatility", "Rolling Volatility"),
    ("rolling_return", "Rolling Return"),
    ("rolling_sharpe", "Rolling Sharpe"),
)


def dataclass_to_dict(obj: Any) -> dict:
    """``dataclasses.asdict`` then recursively NaN/Inf -> null sanitize."""
    return sanitize_obj(dataclasses.asdict(obj))


def _table_or_none(df: "pd.DataFrame | None") -> TableModel | None:
    """Convert a summary frame to a ``TableModel``, or ``None`` when empty/missing.

    The builders return an **empty** ``pd.DataFrame()`` (not ``None``) on their
    no-data paths, so branch on ``.empty`` -- not just ``is None`` (§6).
    """
    if df is None or df.empty:
        return None
    return df_to_table(df)


def _metrics_model(summary: Any) -> TearsheetMetricsModel:
    """Flatten ``TearsheetMetrics`` to the model: strings pass through, numerics
    become finite Python floats or ``None`` (NaN/Inf and numpy scalars handled)."""
    clean: dict[str, Any] = {}
    for key, value in dataclasses.asdict(summary).items():
        if value is None or isinstance(value, str):
            clean[key] = value
            continue
        cleaned = nan_to_none(value)
        clean[key] = float(cleaned) if isinstance(cleaned, (int, float)) and not isinstance(cleaned, bool) else None
    return TearsheetMetricsModel(**clean)


def tearsheet_to_response(result: "TearsheetResult", regime_match_rate: float | None) -> TearsheetResponse:
    """Serialize a ``TearsheetResult`` (+ the service-computed match rate) to JSON."""
    rolling = [
        df_to_series(result.rolling_metrics, name=label, x="date", y=col, meta={"metric": col})
        for col, label in _ROLLING_SERIES
        if col in result.rolling_metrics.columns
    ]
    return TearsheetResponse(
        summary=_metrics_model(result.summary),
        equity_curve=df_to_series(result.equity_curve, name="NAV", x="date", y="nav"),
        drawdown_curve=df_to_series(result.drawdown_curve, name="Drawdown", x="date", y="drawdown"),
        rolling_metrics=rolling,
        exposure_summary=_table_or_none(result.exposure_summary),
        regime_summary=_table_or_none(result.regime_summary),
        benchmark_summary=_table_or_none(result.benchmark_summary),
        regime_match_rate=nan_to_none(regime_match_rate),
    )
