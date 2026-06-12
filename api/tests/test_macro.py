"""Tests for the macro endpoints (10 + 11), Phase 4."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


def test_macro_default_series(client: TestClient) -> None:
    series = client.get("/api/v1/macro").json()["series"]
    names = {s["name"] for s in series}
    assert {"cpi", "pmi", "gs10", "gs2"} <= names
    for s in series:
        assert s["points"]  # NaN-dropped, so each series is non-empty


def test_macro_indicator_filter(client: TestClient) -> None:
    series = client.get("/api/v1/macro", params={"indicators": "cpi,PMI"}).json()["series"]
    assert sorted(s["name"] for s in series) == ["cpi", "pmi"]  # case-normalized


def test_yield_curve_shape_and_spread(client: TestClient) -> None:
    body = client.get("/api/v1/macro/yield-curve").json()
    assert body["gs10"]["name"] == "10Y Yield"
    assert body["gs2"]["name"] == "2Y Yield"
    assert body["spread"]["name"] == "10Y-2Y Spread"
    assert body["spread"]["meta"] == {"fill": "tozeroy"}
    assert body["gs10"]["points"]
    # spread == gs10 - gs2 on the aligned dates (spot-check the first point).
    g10 = body["gs10"]["points"][0]["value"]
    g2 = body["gs2"]["points"][0]["value"]
    sp = body["spread"]["points"][0]["value"]
    assert sp == pytest.approx(g10 - g2)


def test_macro_strict_json(client: TestClient) -> None:
    for path in ("/api/v1/macro", "/api/v1/macro/yield-curve"):
        text = client.get(path).text
        assert "NaN" not in text and "Infinity" not in text
        json.loads(text)
