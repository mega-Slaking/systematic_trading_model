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
    "change": "decimal_change", "dispersion": "ratio", "vov": "percentile",
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


_LEVELS = {"Low", "Normal", "Elevated", "High", "Extreme", "Insufficient history"}


def test_cross_asset_volatility(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/cross-asset")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reference_estimator"] == "rolling_20"
    # Ratio rows carry a pair label + own percentile context.
    pairs = [r["pair"] for r in body["ratios"]]
    assert "TLT / AGG" in pairs
    for r in body["ratios"]:
        assert r["relative_risk_state"] in _LEVELS
        assert r["percentile_ordinal"] is None or 0 <= r["percentile_ordinal"] <= 100
    # Ranking is by raw current vol descending, ranks 1..n, with state visible.
    ranking = body["ranking"]
    assert [row["rank"] for row in ranking] == list(range(1, len(ranking) + 1))
    vols = [row["current_volatility"] for row in ranking if row["current_volatility"] is not None]
    assert vols == sorted(vols, reverse=True)
    assert all(row["confirmed_state"] for row in ranking)
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


@pytest.mark.parametrize("view, unit", [("raw", "ratio"), ("percentile", "percentile")])
def test_cross_asset_ratio_series(client: TestClient, view: str, unit: str) -> None:
    resp = client.get(
        "/api/v1/volatility-features/cross-asset/ratio-series",
        params={"pair": "tlt/agg", "view": view},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pair"] == "TLT / AGG" and body["view"] == view and body["unit"] == unit
    assert body["reference_lines"] == ([0.20, 0.60, 0.80, 0.95] if view == "percentile" else [])
    pts = body["series"][0]["points"]
    assert pts and _ISO_DATE.match(pts[0]["date"])
    if view == "percentile":
        for p in pts:
            assert p["value"] is None or 0.0 <= p["value"] <= 1.0
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_cross_asset_ratio_series_rejects_bad_pair_and_view(client: TestClient) -> None:
    assert client.get(
        "/api/v1/volatility-features/cross-asset/ratio-series", params={"pair": "TLT"}
    ).status_code == 422
    assert client.get(
        "/api/v1/volatility-features/cross-asset/ratio-series", params={"pair": "TLT/AGG", "view": "bogus"}
    ).status_code == 422


_STABILITY = {"Stable", "Changing", "Unstable", "Extreme instability", "Unknown"}


def test_estimate_stability(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/stability", params={"ticker": "tlt"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "TLT"
    assert body["estimate_stability"] in _STABILITY
    sp = body["stability_percentile"]
    assert sp is None or 0.0 <= sp <= 1.0
    assert body["percentile_ordinal"] is None or 0 <= body["percentile_ordinal"] <= 100
    # Raw vol-of-vol is present (debug/methodology) but the percentile/status are the headline.
    assert "raw_vol_of_vol" in body
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_state_table_has_stability(client: TestClient) -> None:
    body = client.get("/api/v1/volatility-features/state-table").json()
    assert body["rows"]
    for row in body["rows"]:
        assert row["estimate_stability"] in _STABILITY
        assert row["stability_percentile"] is None or 0.0 <= row["stability_percentile"] <= 1.0


def test_chart_vov_reference_lines(client: TestClient) -> None:
    body = client.get(
        "/api/v1/volatility-features/chart", params={"ticker": "TLT", "view": "vov"}
    ).json()
    assert body["unit"] == "percentile"
    assert body["reference_lines"] == [0.60, 0.80, 0.95]


# --------------------------------------------------------------------------- #
# Phase 9 — historical signal outcomes
# --------------------------------------------------------------------------- #

_SAMPLE_QUALITY = {"Insufficient sample", "Anecdotal", "Low sample", ""}
_OUTCOME_STATES = {
    "Calm", "Early Expansion", "Stress Expansion", "Persistent Stress",
    "Normalisation", "Shock",
}
_HORIZONS = {"1M", "3M", "6M"}


def test_signal_outcomes_typed_response(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/outcomes", params={"ticker": "tlt"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "TLT"
    assert body["reference_estimator"] == "rolling_20"
    assert body["sampling"] == "non_overlapping"          # default
    assert set(body["horizons"]) == _HORIZONS
    assert isinstance(body["disclaimer"], str) and body["disclaimer"]
    for row in body["rows"]:
        assert row["state"] in _OUTCOME_STATES            # "Unknown" never appears
        assert row["horizon"] in _HORIZONS
        assert isinstance(row["effective_observations"], int)
        assert row["sample_quality"] in _SAMPLE_QUALITY
    # Strict JSON: NaN/Inf -> null at the boundary (gated-out stats are null).
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_signal_outcomes_gating_consistent_with_label(client: TestClient) -> None:
    body = client.get("/api/v1/volatility-features/outcomes", params={"ticker": "TLT"}).json()
    for row in body["rows"]:
        if row["sample_quality"] == "Insufficient sample":
            # No aggregate stats at all.
            for stat in ("mean_return", "median_return", "hit_rate", "worst_return", "best_return"):
                assert row[stat] is None
        elif row["sample_quality"] == "Anecdotal":
            # median / worst / best only — no mean / hit_rate / std.
            assert row["mean_return"] is None
            assert row["hit_rate"] is None
            assert row["std_return"] is None
        # Hit rate, when present, is a fraction.
        if row["hit_rate"] is not None:
            assert 0.0 <= row["hit_rate"] <= 1.0
        # Forward drawdown, when present, is non-positive.
        if row["forward_max_drawdown"] is not None:
            assert row["forward_max_drawdown"] <= 1e-9


def test_signal_outcomes_all_observations_override(client: TestClient) -> None:
    non_overlap = client.get(
        "/api/v1/volatility-features/outcomes", params={"ticker": "TLT", "sampling": "non_overlapping"}
    ).json()
    all_obs = client.get(
        "/api/v1/volatility-features/outcomes", params={"ticker": "TLT", "sampling": "all"}
    ).json()
    assert all_obs["sampling"] == "all"
    # The override never reduces the independent count below the default for any state/horizon.
    by_key = {(r["state"], r["horizon"]): r["effective_observations"] for r in non_overlap["rows"]}
    for r in all_obs["rows"]:
        key = (r["state"], r["horizon"])
        if key in by_key:
            assert r["effective_observations"] >= by_key[key]


def test_signal_outcomes_rejects_unknown_sampling_and_estimator(client: TestClient) -> None:
    assert client.get(
        "/api/v1/volatility-features/outcomes", params={"ticker": "TLT", "sampling": "bogus"}
    ).status_code == 422
    assert client.get(
        "/api/v1/volatility-features/outcomes", params={"ticker": "TLT", "estimator": "bogus"}
    ).status_code == 422


# Combined-condition signals (added incrementally on top of the diagnostic states).
_CONDITIONS = {
    "Vol rising + price falling",
    "Vol rising + price rising",
    "Vol falling after High/Extreme",
    "20D/60D in expansion",
    "Estimator agreement Low",
    "TLT/AGG relative vol > 90th pct",
}


def test_signal_outcome_conditions_typed_response(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/outcomes/conditions", params={"ticker": "tlt"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "TLT"
    assert body["sampling"] == "non_overlapping"           # default
    assert set(body["horizons"]) == _HORIZONS
    seen_conditions = {row["state"] for row in body["rows"]}
    # Every single-asset condition appears (TLT/AGG cross-asset condition appears
    # whenever both assets exist in the surface).
    assert {
        "Vol rising + price falling", "Vol rising + price rising",
        "Vol falling after High/Extreme", "20D/60D in expansion", "Estimator agreement Low",
    } <= seen_conditions
    assert seen_conditions <= _CONDITIONS
    for row in body["rows"]:
        assert row["horizon"] in _HORIZONS
        assert isinstance(row["effective_observations"], int)
        assert row["sample_quality"] in _SAMPLE_QUALITY
        # Same gating contract as the state table.
        if row["sample_quality"] == "Insufficient sample":
            assert row["mean_return"] is None
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_signal_outcome_conditions_includes_cross_asset_when_tlt_agg_present(client: TestClient) -> None:
    # TLT and AGG are both in the production surface, so the cross-asset condition
    # must actually appear (guards against _tlt_agg_relative_percentile silently
    # returning empty and dropping the condition).
    body = client.get("/api/v1/volatility-features/outcomes/conditions", params={"ticker": "TLT"}).json()
    seen = {row["state"] for row in body["rows"]}
    assert "TLT/AGG relative vol > 90th pct" in seen


def test_signal_outcome_conditions_rejects_bad_params(client: TestClient) -> None:
    assert client.get(
        "/api/v1/volatility-features/outcomes/conditions", params={"ticker": "TLT", "sampling": "bogus"}
    ).status_code == 422
    assert client.get(
        "/api/v1/volatility-features/outcomes/conditions", params={"ticker": "TLT", "estimator": "bogus"}
    ).status_code == 422


def test_signal_outcome_distribution_typed_response(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/volatility-features/outcomes/distribution", params={"ticker": "TLT", "horizon": "3M"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "TLT"
    assert body["horizon"] == "3M"
    assert body["unit"] == "decimal"
    for dist in body["distributions"]:
        assert dist["state"] in _OUTCOME_STATES
        # effective_observations is the length of the realised-return sample, all finite.
        assert dist["effective_observations"] == len(dist["returns"])
        assert all(isinstance(v, (int, float)) for v in dist["returns"])
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_signal_outcome_distribution_rejects_bad_horizon(client: TestClient) -> None:
    assert client.get(
        "/api/v1/volatility-features/outcomes/distribution", params={"ticker": "TLT", "horizon": "9Y"}
    ).status_code == 422


def test_volatility_snapshot_typed_response(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/snapshot", params={"ticker": "tlt"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "TLT"
    assert body["reference_estimator"] == "rolling_20"
    # Reproducibility metadata is always present (never a state without its context).
    assert body["config_key"] and body["state_config_version"] and body["agreement_config_version"]
    assert body["confirmation_days"] > 0
    assert body["historical_window"] == "5Y" and body["stability_window"] == "5Y"
    # Lagged surface => as_of (t) and information_through (t-1) are present and distinct.
    assert _ISO_DATE.match(body["as_of_date"])
    assert _ISO_DATE.match(body["information_through_date"])
    assert body["as_of_date"] != body["information_through_date"]
    # Diagnostic fields exposed.
    for fld in ("volatility_level", "direction", "confirmed_state", "instantaneous_state",
                "estimator_agreement", "price_volatility_context", "estimate_stability"):
        assert isinstance(body[fld], str)
    # Strict JSON: NaN/Inf -> null.
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_volatility_snapshot_historical_as_of(client: TestClient) -> None:
    base = client.get("/api/v1/volatility-features/snapshot", params={"ticker": "TLT"}).json()
    info_through = base["information_through_date"]
    assert info_through  # there is a prior trading day
    hist = client.get(
        "/api/v1/volatility-features/snapshot", params={"ticker": "TLT", "as_of": info_through}
    ).json()
    # Requesting an earlier as-of returns that historical snapshot, not the latest.
    assert hist["as_of_date"] == info_through
    assert hist["as_of_date"] != base["as_of_date"]


def test_volatility_snapshot_rejects_unknown_estimator(client: TestClient) -> None:
    assert client.get(
        "/api/v1/volatility-features/snapshot", params={"ticker": "TLT", "estimator": "bogus"}
    ).status_code == 422


def test_volatility_cross_asset_snapshot(client: TestClient) -> None:
    resp = client.get("/api/v1/volatility-features/snapshot/cross-asset")
    assert resp.status_code == 200
    body = resp.json()
    assert body["config_key"] and body["state_config_version"]
    assert len(body["assets"]) >= 1
    # Ranking covers the assets, ranks are 1..n in order.
    ranks = [r["rank"] for r in body["ranking"]]
    assert ranks == list(range(1, len(ranks) + 1))
    for a in body["assets"]:
        assert isinstance(a["confirmed_state"], str)
    assert "NaN" not in resp.text and "Infinity" not in resp.text
    json.loads(resp.text)


def test_signal_outcome_distribution_non_overlapping_subset_of_all(client: TestClient) -> None:
    # Non-overlapping (default) must never have more samples per state than "all".
    non = client.get(
        "/api/v1/volatility-features/outcomes/distribution",
        params={"ticker": "TLT", "horizon": "1M", "sampling": "non_overlapping"},
    ).json()
    allobs = client.get(
        "/api/v1/volatility-features/outcomes/distribution",
        params={"ticker": "TLT", "horizon": "1M", "sampling": "all"},
    ).json()
    all_counts = {d["state"]: d["effective_observations"] for d in allobs["distributions"]}
    for d in non["distributions"]:
        assert d["effective_observations"] <= all_counts.get(d["state"], 0)
