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


# --------------------------------------------------------------------------- #
# Derived indicators (Phase 1: server-side derivation + honest meta)
# --------------------------------------------------------------------------- #
def test_macro_default_includes_derived_series(client: TestClient) -> None:
    names = {s["name"] for s in client.get("/api/v1/macro").json()["series"]}
    # Raw keys preserved (backward compat) AND derived keys now present.
    assert {"cpi", "pmi"} <= names
    assert {"cpi_yoy", "real_policy_rate", "curve_spread"} <= names


def test_derived_indicators_selectable_with_meta(client: TestClient) -> None:
    series = client.get(
        "/api/v1/macro", params={"indicators": "cpi_yoy,real_policy_rate,curve_spread"}
    ).json()["series"]
    assert sorted(s["name"] for s in series) == ["cpi_yoy", "curve_spread", "real_policy_rate"]
    by_name = {s["name"]: s for s in series}
    for s in series:
        assert s["points"]  # NaN-dropped but populated on the real DB
        assert s["meta"] and s["meta"]["unit"] and s["meta"]["source"]
    assert by_name["cpi_yoy"]["meta"]["unit"] == "pct_frac"
    assert by_name["real_policy_rate"]["meta"]["unit"] == "pp"
    assert by_name["curve_spread"]["meta"]["unit"] == "pp"


def test_cpi_yoy_values_are_decimal_fractions(client: TestClient) -> None:
    # Guards the "no × 100" decision end-to-end: YoY inflation stays ~0.0x, never ~3.x.
    points = client.get("/api/v1/macro", params={"indicators": "cpi_yoy"}).json()["series"][0]["points"]
    values = [p["value"] for p in points if p["value"] is not None]
    assert values and max(abs(v) for v in values) < 1.0


def test_raw_cpi_and_cfnai_meta_corrects_legacy_mislabels(client: TestClient) -> None:
    series = client.get("/api/v1/macro", params={"indicators": "cpi,pmi"}).json()["series"]
    by_name = {s["name"]: s for s in series}
    # `cpi` is an index level, explicitly NOT YoY.
    assert by_name["cpi"]["meta"]["unit"] == "level"
    assert by_name["cpi"]["meta"]["source"] == "CPIAUCSL"
    assert "NOT" in by_name["cpi"]["meta"]["note"].upper()
    # `pmi` is actually CFNAI, neutral 0.
    assert by_name["pmi"]["meta"]["source"] == "CFNAI"
    assert by_name["pmi"]["meta"]["neutral"] == 0


def test_macro_strict_json_with_derived(client: TestClient) -> None:
    text = client.get("/api/v1/macro", params={"indicators": ",".join([
        "cpi_yoy", "cpi_yoy_change_3m", "core_cpi_yoy", "real_policy_rate",
        "curve_spread", "yield_10y_change_3m", "unemployment_minus_12m_low",
    ])}).text
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text)


# --------------------------------------------------------------------------- #
# Yield-curve regime + inversion shading (Phase 2)
# --------------------------------------------------------------------------- #
_CURVE_REGIME_LABELS = {
    "Bull steepening", "Bull flattening", "Bear flattening", "Bear steepening", "Mixed",
}


def test_yield_curve_regime_categorical_shape(client: TestClient) -> None:
    body = client.get("/api/v1/macro/yield-curve").json()
    regime = body["curve_regime"]
    assert regime["name"] == "Curve Regime"
    # categories map covers all five regimes; points carry numeric code + label.
    assert set(regime["categories"].values()) == _CURVE_REGIME_LABELS
    labelled = [p for p in regime["points"] if p["label"] is not None]
    assert labelled, "expected some classified points"
    for p in labelled:
        assert p["label"] in _CURVE_REGIME_LABELS
        assert isinstance(p["value"], (int, float))  # ordinal code
        # the point's code maps back to its label via the categories table.
        assert regime["categories"][str(int(p["value"]))] == p["label"]


def test_yield_curve_inverted_intervals_and_current_regime(client: TestClient) -> None:
    body = client.get("/api/v1/macro/yield-curve").json()
    assert isinstance(body["inverted_intervals"], list)
    for span in body["inverted_intervals"]:
        assert set(span) == {"start", "end"}
        assert span["start"] <= span["end"]  # ISO dates sort lexicographically
    assert body["current_regime"] is None or body["current_regime"] in _CURVE_REGIME_LABELS


def test_yield_curve_strict_json_with_regime(client: TestClient) -> None:
    text = client.get("/api/v1/macro/yield-curve").text
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text)


# --------------------------------------------------------------------------- #
# Macro snapshot cards (Phase 3)
# --------------------------------------------------------------------------- #
def test_snapshot_cards_shape(client: TestClient) -> None:
    body = client.get("/api/v1/macro/snapshot").json()
    assert body["as_of"]
    cards = {c["key"]: c for c in body["cards"]}
    # Headline numeric cards + the categorical curve-regime card are present.
    assert {"cpi_yoy", "unemployment", "gs10", "curve_spread", "curve_regime"} <= set(cards)
    for c in body["cards"]:
        assert c["observation_date"]  # per-card date (never shared)
        assert isinstance(c["is_stale"], bool)


def test_snapshot_units_and_value_types(client: TestClient) -> None:
    cards = {c["key"]: c for c in client.get("/api/v1/macro/snapshot").json()["cards"]}
    assert cards["cpi_yoy"]["unit"] == "pct_frac"
    assert abs(cards["cpi_yoy"]["value"]) < 1.0  # decimal fraction, not × 100
    assert cards["curve_spread"]["unit"] == "pp"
    # Categorical card: string value, no unit, no direction.
    cr = cards["curve_regime"]
    assert isinstance(cr["value"], str) and cr["unit"] is None and cr["direction"] is None


def test_snapshot_direction_matches_change_sign(client: TestClient) -> None:
    for c in client.get("/api/v1/macro/snapshot").json()["cards"]:
        if c["change_3m"] is None:
            continue
        expected = "up" if c["change_3m"] > 0 else "down" if c["change_3m"] < 0 else "flat"
        assert c["direction"] == expected


def test_snapshot_strict_json(client: TestClient) -> None:
    text = client.get("/api/v1/macro/snapshot").text
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text)


def test_snapshot_includes_macro_regime_card(client: TestClient) -> None:
    cards = {c["key"]: c for c in client.get("/api/v1/macro/snapshot").json()["cards"]}
    assert "macro_regime" in cards
    mr = cards["macro_regime"]
    assert isinstance(mr["value"], str) and mr["unit"] is None and mr["direction"] is None


# --------------------------------------------------------------------------- #
# Macro-regime timeline (Phase 4)
# --------------------------------------------------------------------------- #
_MACRO_REGIME_LABELS = {
    "Stable Growth", "Inflationary Tightening", "Disinflationary Slowdown",
    "Stagflation Risk", "Easing Transition",
}


def test_regime_timeline_shape_and_legend(client: TestClient) -> None:
    body = client.get("/api/v1/macro/regime-timeline").json()
    regime = body["regime"]
    assert regime["name"] == "Macro Regime"
    assert set(regime["categories"].values()) == _MACRO_REGIME_LABELS
    # Legend covers every regime with a (prior) description.
    assert set(body["legend"]) == _MACRO_REGIME_LABELS
    assert all(body["legend"].values())
    labelled = [p for p in regime["points"] if p["label"] is not None]
    assert labelled
    for p in labelled:
        assert p["label"] in _MACRO_REGIME_LABELS
        assert regime["categories"][str(int(p["value"]))] == p["label"]


def test_regime_timeline_engine_overlay(client: TestClient) -> None:
    engine = client.get("/api/v1/macro/regime-timeline").json()["engine_regime"]
    # Present when the backtest regime trace is populated; tolerate None otherwise.
    if engine is not None:
        assert set(engine["categories"].values()) == {"No duration support", "Supports duration"}
        for p in engine["points"]:
            if p["label"] is not None:
                assert p["label"] in {"No duration support", "Supports duration"}


def test_regime_timeline_strict_json(client: TestClient) -> None:
    text = client.get("/api/v1/macro/regime-timeline").text
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text)


# --------------------------------------------------------------------------- #
# Conditional forward returns (Phase 5)
# --------------------------------------------------------------------------- #
def test_conditional_returns_shape_and_flags(client: TestClient) -> None:
    body = client.get("/api/v1/macro/conditional-returns").json()
    assert body["is_lagged"] is True
    assert body["point_in_time_release_available"] is False
    assert any("not independent" in n.lower() or "overlap" in n.lower() for n in body["notes"])
    cols = body["table"]["columns"]
    for c in ["regime", "etf", "n", "next_1m_mean", "next_3m_mean", "next_12m_mean", "hit_rate_3m", "median_3m", "thin"]:
        assert c in cols
    rows = body["table"]["rows"]
    assert rows  # the populated DB yields regime × ETF rows
    etfs = {r["etf"] for r in rows}
    assert etfs <= {"TLT", "AGG", "SHY"} and etfs  # all three by default
    for r in rows:
        assert isinstance(r["thin"], bool)
        assert isinstance(r["n"], int)


def test_conditional_returns_etf_filter(client: TestClient) -> None:
    rows = client.get("/api/v1/macro/conditional-returns", params={"etf": "TLT"}).json()["table"]["rows"]
    assert rows and all(r["etf"] == "TLT" for r in rows)


def test_conditional_returns_min_observations_flags_thin(client: TestClient) -> None:
    # A very high threshold makes every regime row 'thin'.
    rows = client.get("/api/v1/macro/conditional-returns", params={"min_observations": 100000}).json()["table"]["rows"]
    assert rows and all(r["thin"] for r in rows)


def test_conditional_returns_strict_json(client: TestClient) -> None:
    text = client.get("/api/v1/macro/conditional-returns").text
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text)


# --------------------------------------------------------------------------- #
# Forward-return scatter (Phase 5 explorer display mode)
# --------------------------------------------------------------------------- #
def test_forward_return_scatter_shape(client: TestClient) -> None:
    body = client.get(
        "/api/v1/macro/forward-return-scatter",
        params={"etf": "TLT", "indicator": "cpi_yoy_change_3m", "horizon": "3m"},
    ).json()
    assert body["etf"] == "TLT" and body["horizon"] == "3m" and body["x_key"] == "cpi_yoy_change_3m"
    assert body["x_unit"] == "pct_frac" and body["x_label"]
    assert body["n"] == len(body["points"]) and body["points"]
    for p in body["points"]:
        assert isinstance(p["x"], (int, float)) and isinstance(p["y"], (int, float)) and p["date"]
    assert "not causation" in body["note"].lower()


def test_forward_return_scatter_unknown_indicator_422(client: TestClient) -> None:
    r = client.get("/api/v1/macro/forward-return-scatter", params={"indicator": "not_a_real_indicator"})
    assert r.status_code == 422


def test_forward_return_scatter_strict_json(client: TestClient) -> None:
    text = client.get("/api/v1/macro/forward-return-scatter").text
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text)
