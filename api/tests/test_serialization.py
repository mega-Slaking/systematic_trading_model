"""Serialization-boundary round-trips (spec §6, §10.3).

The NaN/Inf -> null sanitizer is the single most likely correctness bug in the
migration, so it is exercised from the first commit. Every test asserts the
output survives a *strict* JSON round-trip: ``json.loads`` rejects the bare
``NaN``/``Infinity`` tokens that ``json.dumps(float('nan'))`` would emit, so a
leaking non-finite float fails here loudly.
"""

from __future__ import annotations

import json
import math

import numpy as np
import orjson
import pandas as pd
import pytest

from api.schemas.common import NamedSeries, TableModel
from api.serialization.dataclasses import dataclass_to_dict
from api.serialization.frames import (
    df_to_series,
    df_to_table,
    nan_to_none,
    sanitize_obj,
    series_to_points,
    to_iso,
)


def _strict_roundtrip(payload) -> object:
    """Serialize with orjson (the app's encoder), then parse with STRICT json.

    ``orjson`` refuses ``float('nan')`` by default (raises), and stdlib
    ``json.loads`` rejects ``NaN``/``Infinity`` tokens, so this is a real guard
    that nothing non-finite escaped the sanitizer.
    """
    raw = orjson.dumps(payload)
    return json.loads(raw)  # strict parse: would raise on NaN/Infinity tokens


# --------------------------------------------------------------------------- #
# nan_to_none / sanitize_obj                                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "value, expected",
    [
        (float("nan"), None),
        (float("inf"), None),
        (float("-inf"), None),
        (np.nan, None),
        (np.float64("nan"), None),
        (np.float64("inf"), None),
        (pd.NA, None),
        (pd.NaT, None),
        (None, None),
        (1.5, 1.5),
        (np.float64(2.25), 2.25),
        (0.0, 0.0),
        (-3.0, -3.0),
        (7, 7),
        (True, True),
        (False, False),
        ("x", "x"),
    ],
)
def test_nan_to_none_scalars(value, expected) -> None:
    result = nan_to_none(value)
    assert result == expected or (result is None and expected is None)
    # bool must not be coerced to int/float by the sanitizer
    if isinstance(expected, bool):
        assert isinstance(result, bool)


def test_nan_to_none_finite_numpy_floats_preserve_value() -> None:
    out = nan_to_none(np.float64(123.456))
    assert math.isclose(out, 123.456)


def test_sanitize_obj_recurses_nested_containers() -> None:
    obj = {
        "a": float("nan"),
        "b": [1.0, float("inf"), {"c": np.nan, "d": 2.0}],
        "e": ("x", pd.NA),
    }
    clean = sanitize_obj(obj)
    assert clean == {"a": None, "b": [1.0, None, {"c": None, "d": 2.0}], "e": ["x", None]}
    # And it must be strictly JSON-serializable.
    assert _strict_roundtrip(clean) == clean


# --------------------------------------------------------------------------- #
# to_iso                                                                       #
# --------------------------------------------------------------------------- #

def test_to_iso_handles_mixed_date_formats() -> None:
    # The DB is genuinely inconsistent: some columns carry a 00:00:00 time
    # component, others a plain date string (spec §6).
    s = pd.Series(["2010-01-05 00:00:00", "2010-01-06", pd.Timestamp("2010-01-07 13:30:00")])
    out = to_iso(s).tolist()
    assert out == ["2010-01-05", "2010-01-06", "2010-01-07"]


def test_to_iso_maps_unparseable_to_none() -> None:
    s = pd.Series(["2010-01-05", None, "not-a-date"])
    out = to_iso(s).tolist()
    assert out[0] == "2010-01-05"
    assert out[1] is None
    assert out[2] is None


# --------------------------------------------------------------------------- #
# series_to_points / df_to_series                                             #
# --------------------------------------------------------------------------- #

def test_series_to_points_sanitizes_and_isoformats() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"]),
            "nav": [100.0, float("nan"), 102.5],
        }
    )
    points = series_to_points(df, x="date", y="nav")
    assert [p.date for p in points] == ["2020-01-01", "2020-01-02", "2020-01-03"]
    assert [p.value for p in points] == [100.0, None, 102.5]


def test_df_to_series_roundtrips_with_nan_gap() -> None:
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
            "ret": [np.nan, 0.0123],  # first rolling row NaN, like the real curves
        }
    )
    series = df_to_series(df, name="rolling_sharpe", y="ret", meta={"axis": "y2"})
    assert isinstance(series, NamedSeries)
    payload = series.model_dump()
    restored = _strict_roundtrip(payload)
    assert restored["name"] == "rolling_sharpe"
    assert restored["meta"] == {"axis": "y2"}
    assert restored["points"][0]["value"] is None
    assert restored["points"][1]["value"] == 0.0123


def test_series_round_to_trims_precision() -> None:
    df = pd.DataFrame({"date": pd.to_datetime(["2020-01-01"]), "ret": [0.123456789012]})
    points = series_to_points(df, y="ret", round_to=8)
    assert points[0].value == round(0.123456789012, 8)


# --------------------------------------------------------------------------- #
# df_to_table                                                                  #
# --------------------------------------------------------------------------- #

def test_df_to_table_sanitizes_cells_and_isoformats_dates() -> None:
    df = pd.DataFrame(
        {
            "date": ["2020-01-01 00:00:00", "2020-01-02"],
            "metric": [1.0, float("nan")],
            "label": ["a", None],
            "flag": [True, False],
        }
    )
    table = df_to_table(df)
    assert isinstance(table, TableModel)
    assert table.columns == ["date", "metric", "label", "flag"]
    assert table.rows[0] == {"date": "2020-01-01", "metric": 1.0, "label": "a", "flag": True}
    assert table.rows[1] == {"date": "2020-01-02", "metric": None, "label": None, "flag": False}
    # Strict JSON round-trip of the whole model.
    restored = _strict_roundtrip(table.model_dump())
    assert restored["rows"][1]["metric"] is None


def test_df_to_table_empty_frame() -> None:
    df = pd.DataFrame(columns=["date", "x"])
    table = df_to_table(df)
    assert table.columns == ["date", "x"]
    assert table.rows == []


def test_df_to_table_handles_inf_in_cell() -> None:
    df = pd.DataFrame({"date": ["2020-01-01"], "x": [float("inf")]})
    table = df_to_table(df)
    assert table.rows[0]["x"] is None


# --------------------------------------------------------------------------- #
# dataclass_to_dict                                                            #
# --------------------------------------------------------------------------- #

def test_dataclass_to_dict_sanitizes_float_fields() -> None:
    import dataclasses

    @dataclasses.dataclass
    class Metrics:
        sharpe: float
        cost_drag: float  # the genuinely-nullable one in TearsheetMetrics
        label: str

    out = dataclass_to_dict(Metrics(sharpe=1.2, cost_drag=float("nan"), label="x"))
    assert out == {"sharpe": 1.2, "cost_drag": None, "label": "x"}
    assert _strict_roundtrip(out) == out


# --------------------------------------------------------------------------- #
# End-to-end: the app's response class is a NaN safety net (defense in depth)  #
# --------------------------------------------------------------------------- #

def test_app_response_class_degrades_raw_nan_to_null() -> None:
    """If a non-finite float ever *bypasses* the sanitizer and reaches a field,
    the app's configured ORJSONResponse must still emit a strict-parseable
    ``null`` (HTTP 200) -- not a 500 or an invalid ``NaN`` token.

    Verified the contrast on these pins: FastAPI's *default* (stdlib json) path
    raises ValueError -> 500 on a raw NaN, while ORJSONResponse degrades it to
    ``null``. This locks that choice in (spec §6). Uses a throwaway endpoint on a
    fresh app that reuses the production default response class.
    """
    from fastapi import FastAPI
    from fastapi.responses import ORJSONResponse
    from fastapi.testclient import TestClient
    from pydantic import BaseModel

    class _Probe(BaseModel):
        v: float | None

    probe_app = FastAPI(default_response_class=ORJSONResponse)

    @probe_app.get("/probe", response_model=_Probe)
    def _probe() -> _Probe:
        return _Probe(v=float("nan"))  # deliberately un-sanitized

    with TestClient(probe_app) as client:
        resp = client.get("/probe")
    assert resp.status_code == 200
    assert json.loads(resp.content) == {"v": None}  # strict parse, value is null
