"""Tests for the volatility-features endpoints (8 + 9), Phase 4."""

from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_METHODS = ["rolling_20", "rolling_60", "ewma_94", "ewma_97", "garch"]


def test_volatility_features_for_ticker(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features", params={"ticker": "tlt"})  # case-insensitive
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "TLT"
    assert body["available_methods"]
    assert body["series"]
    s0 = body["series"][0]
    assert s0["points"] and _ISO_DATE.match(s0["points"][0]["date"])
    assert s0["meta"] and s0["meta"]["method"] in _METHODS


def test_volatility_features_methods_filter(client: TestClient) -> None:
    body = client.get("/api/v1/volatility-features", params={"ticker": "TLT", "methods": "garch"}).json()
    assert [s["meta"]["method"] for s in body["series"]] == ["garch"]


def test_volatility_features_requires_ticker(client: TestClient) -> None:
    assert client.get("/api/v1/volatility-features").status_code == 422


def test_volatility_latest(client: TestClient) -> None:
    body = client.get("/api/v1/volatility-features/latest").json()
    assert body["methods"] == _METHODS
    assert body["rows"]
    row = body["rows"][0]
    assert "ticker" in row and "garch" in row
    assert row["date"] is None or _ISO_DATE.match(row["date"])


def test_volatility_strict_json(client: TestClient) -> None:
    for path, params in (("/api/v1/volatility-features", {"ticker": "TLT"}), ("/api/v1/volatility-features/latest", {})):
        text = client.get(path, params=params).text
        assert "NaN" not in text and "Infinity" not in text
        json.loads(text)
