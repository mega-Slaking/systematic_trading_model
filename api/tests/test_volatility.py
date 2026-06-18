"""Tests for the volatility-features endpoints (8 + 9), Phase 4."""

from __future__ import annotations

import json
import re

import pytest
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


def test_volatility_audit(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["warnings"], list)
    assert isinstance(body["config_keys"], list)
    assert isinstance(body["n_rows"], int)
    # Diagnostic endpoint must be strict JSON like the rest of the surface.
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_volatility_context(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/context", params={"ticker": "tlt"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "TLT"
    assert body["reference_estimator"] == "rolling_20"
    assert body["historical_window"] == "5Y"
    assert body["volatility_level"] in {
        "Low", "Normal", "Elevated", "High", "Extreme", "Insufficient history",
    }
    # Percentile is a 0..1 decimal (or null); ordinal is 0..100 (or null).
    pct = body["historical_percentile"]
    assert pct is None or 0.0 <= pct <= 1.0
    ordinal = body["percentile_ordinal"]
    assert ordinal is None or 0 <= ordinal <= 100
    # as_of is t, information_through_date is t-1 (strictly earlier) when present.
    if body["as_of_date"] and body["information_through_date"]:
        assert body["information_through_date"] < body["as_of_date"]
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_volatility_context_rejects_unknown_estimator_and_window(client: TestClient) -> None:
    assert client.get(
        "/api/v1/volatility-features/context", params={"ticker": "TLT", "estimator": "bogus"}
    ).status_code == 422
    assert client.get(
        "/api/v1/volatility-features/context", params={"ticker": "TLT", "window": "7Y"}
    ).status_code == 422


def test_volatility_percentile_series(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/volatility-features/percentile", params={"ticker": "TLT", "window": "5Y"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["unit"] == "percentile"
    assert body["reference_lines"] == [0.20, 0.60, 0.80, 0.95]
    assert body["series"]
    pts = body["series"][0]["points"]
    assert pts and _ISO_DATE.match(pts[0]["date"])
    # Every non-null percentile point is a 0..1 decimal.
    for p in pts:
        assert p["value"] is None or 0.0 <= p["value"] <= 1.0
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_volatility_context_has_direction_and_term_fields(client: TestClient) -> None:
    body = client.get("/api/v1/volatility-features/context", params={"ticker": "TLT"}).json()
    assert body["direction"] in {"Rising", "Falling", "Stable", "Unknown"}
    assert body["term_state"] in {"Expansion", "Balanced", "Contraction", "Unknown"}
    for field in ("change_5d", "change_20d", "term_ratio"):
        assert body[field] is None or isinstance(body[field], (int, float))


def test_volatility_derived_ratio(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/derived", params={"ticker": "TLT", "view": "ratio"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["view"] == "ratio" and body["unit"] == "ratio"
    assert body["reference_lines"] == [0.85, 1.00, 1.15]
    assert [s["name"] for s in body["series"]] == ["20D / 60D ratio"]
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_volatility_derived_change(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/derived", params={"ticker": "TLT", "view": "change"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["view"] == "change" and body["unit"] == "relative_change"
    assert body["reference_lines"] == [-0.10, 0.00, 0.10]
    assert [s["name"] for s in body["series"]] == ["20-day change", "5-day change"]
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_volatility_derived_rejects_unknown_view(client: TestClient) -> None:
    assert client.get(
        "/api/v1/volatility-features/derived", params={"ticker": "TLT", "view": "bogus"}
    ).status_code == 422


_STATES = {
    "Calm", "Early Expansion", "Stress Expansion", "Persistent Stress",
    "Normalisation", "Shock", "Unknown",
}


def test_volatility_context_has_state_fields(client: TestClient) -> None:
    body = client.get("/api/v1/volatility-features/context", params={"ticker": "TLT"}).json()
    assert body["instantaneous_state"] in _STATES
    assert body["confirmed_state"] in _STATES
    assert isinstance(body["state_explanation"], str) and body["state_explanation"]
    assert isinstance(body["state_config_version"], str) and body["state_config_version"]


def test_volatility_state_table(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/state-table")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"]
    assert body["as_of_date"] is None or _ISO_DATE.match(body["as_of_date"])
    for row in body["rows"]:
        assert row["confirmed_state"] in _STATES
        assert row["term_state"] in {"Expansion", "Balanced", "Contraction", "Unknown"}
        assert row["percentile_ordinal"] is None or 0 <= row["percentile_ordinal"] <= 100
    # One row per asset, strict JSON.
    assert len({r["ticker"] for r in body["rows"]}) == len(body["rows"])
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_volatility_state_table_rejects_unknown_estimator(client: TestClient) -> None:
    assert client.get(
        "/api/v1/volatility-features/state-table", params={"estimator": "bogus"}
    ).status_code == 422


def test_volatility_context_has_agreement_fields(client: TestClient) -> None:
    body = client.get("/api/v1/volatility-features/context", params={"ticker": "TLT"}).json()
    assert body["estimator_agreement"] in {"High", "Moderate", "Low", "Unknown"}
    assert body["absolute_spread"] is None or body["absolute_spread"] >= 0
    assert body["relative_dispersion"] is None or body["relative_dispersion"] >= 0
    assert isinstance(body["agreement_config_version"], str) and body["agreement_config_version"]


def test_volatility_agreement_panel(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/agreement", params={"ticker": "TLT"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["agreement"] in {"High", "Moderate", "Low", "Unknown"}
    methods = {r["method"] for r in body["rows"]}
    assert methods <= set(_METHODS) and methods           # rows are real estimators
    for r in body["rows"]:
        assert r["historical_percentile_ordinal"] is None or 0 <= r["historical_percentile_ordinal"] <= 100
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_volatility_derived_dispersion(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/derived", params={"ticker": "TLT", "view": "dispersion"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["view"] == "dispersion" and body["unit"] == "ratio"
    assert body["reference_lines"] == [0.10, 0.25]
    assert [s["name"] for s in body["series"]] == ["Estimator dispersion"]
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


_PRICE_CONTEXTS = {
    "Adverse Shock", "Positive Volatility Expansion", "Stable Positive Trend",
    "Controlled Decline", "Quiet / Range-Bound", "Unknown",
}


def test_volatility_context_has_price_context_fields(client: TestClient) -> None:
    body = client.get("/api/v1/volatility-features/context", params={"ticker": "TLT"}).json()
    assert body["price_volatility_context"] in _PRICE_CONTEXTS
    assert body["asset_return_20d"] is None or isinstance(body["asset_return_20d"], (int, float))
    # vol_change_20d mirrors the Phase 2 change_20d.
    assert body["vol_change_20d"] == body["change_20d"]


def test_volatility_state_table_has_price_context(client: TestClient) -> None:
    body = client.get("/api/v1/volatility-features/state-table").json()
    assert body["rows"]
    for row in body["rows"]:
        assert row["price_volatility_context"] in _PRICE_CONTEXTS
        assert row["asset_return_20d"] is None or isinstance(row["asset_return_20d"], (int, float))


_CHART_UNITS = {
    "volatility": "decimal", "percentile": "percentile", "ratio": "ratio",
    "change": "decimal_change", "dispersion": "ratio",
}


@pytest.mark.parametrize("view, unit", list(_CHART_UNITS.items()))
def test_volatility_chart_views(client: TestClient, view: str, unit: str) -> None:
    resp = client.get("/api/v1/volatility-features/chart", params={"ticker": "TLT", "view": view})
    assert resp.status_code == 200
    body = resp.json()
    assert body["view_mode"] == view and body["unit"] == unit
    assert body["series"] and body["series"][0]["points"]
    assert all(s["unit"] == unit for s in body["series"])
    # The volatility view returns one trace per estimator; others a single line (change=2).
    assert len(body["series"]) == (len(_METHODS) if view == "volatility" else (2 if view == "change" else 1))
    # State ranges are contiguous + non-overlapping; transitions carry metadata.
    ends = [r["end"] for r in body["state_ranges"]]
    starts = [r["start"] for r in body["state_ranges"]]
    assert all(starts[i] > ends[i - 1] for i in range(1, len(starts)))
    for t in body["transitions"]:
        assert t["kind"].startswith("entered_") and _ISO_DATE.match(t["date"])
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_volatility_chart_rejects_unknown_view(client: TestClient) -> None:
    assert client.get(
        "/api/v1/volatility-features/chart", params={"ticker": "TLT", "view": "bogus"}
    ).status_code == 422
