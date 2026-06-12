"""Tests for the tearsheet (5) and daily-rows (4) endpoints, Phase 3.

Run against the populated repo DB. The tearsheet is the one real compute path,
so these exercise ``build_tearsheet`` end-to-end through the serializer.
"""

from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _first_scenario(client: TestClient) -> str:
    return client.get("/api/v1/scenarios").json()["scenarios"][0]


# --------------------------------------------------------------------------- #
# Endpoint 5: /tearsheet/{scenario_id}
# --------------------------------------------------------------------------- #
def test_tearsheet_full_shape(client: TestClient) -> None:
    sid = _first_scenario(client)
    resp = client.get(f"/api/v1/tearsheet/{sid}")
    assert resp.status_code == 200
    body = resp.json()

    summary = body["summary"]
    assert summary["scenario_id"] == sid
    assert _ISO_DATE.match(summary["start_date"]) and _ISO_DATE.match(summary["end_date"])
    # All 26 dataclass fields present.
    assert len(summary) == 26
    assert {"total_return", "sharpe", "sortino", "calmar", "cvar_95", "cost_drag"} <= set(summary)

    assert body["equity_curve"]["name"] == "NAV" and body["equity_curve"]["points"]
    assert body["drawdown_curve"]["name"] == "Drawdown" and body["drawdown_curve"]["points"]
    assert _ISO_DATE.match(body["equity_curve"]["points"][0]["date"])

    rolling_names = [s["name"] for s in body["rolling_metrics"]]
    assert "Rolling Sharpe" in rolling_names

    for key in ("exposure_summary", "regime_summary", "benchmark_summary"):
        table = body[key]
        assert table is None or ("columns" in table and "rows" in table)

    mr = body["regime_match_rate"]
    assert mr is None or (0.0 <= mr <= 1.0)


def test_tearsheet_emits_strict_json_with_params(client: TestClient) -> None:
    sid = _first_scenario(client)
    resp = client.get(f"/api/v1/tearsheet/{sid}", params={"risk_free_rate": 0.0, "periods_per_year": 252})
    assert resp.status_code == 200
    text = resp.text
    assert "NaN" not in text and "Infinity" not in text  # §6/§10.3
    json.loads(text)


def test_tearsheet_is_referentially_transparent(client: TestClient) -> None:
    """Same DB state + params -> identical JSON (deterministic + cached, §5.2)."""
    sid = _first_scenario(client)
    first = client.get(f"/api/v1/tearsheet/{sid}").json()
    second = client.get(f"/api/v1/tearsheet/{sid}").json()
    assert first == second


def test_tearsheet_unknown_scenario_404(client: TestClient) -> None:
    resp = client.get("/api/v1/tearsheet/does_not_exist")
    assert resp.status_code == 404
    assert "detail" in resp.json()


# --------------------------------------------------------------------------- #
# Endpoint 4: /backtest-results/{scenario_id}/daily
# --------------------------------------------------------------------------- #
def test_daily_rows_default_columns_and_pagination(client: TestClient) -> None:
    sid = _first_scenario(client)
    resp = client.get(f"/api/v1/backtest-results/{sid}/daily", params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario_id"] == sid and body["limit"] == 5
    assert body["total_rows"] > 5
    table = body["table"]
    assert len(table["rows"]) == 5
    assert "nav" in table["columns"]
    assert "weights" not in table["columns"]  # excluded from the default scalar set
    assert _ISO_DATE.match(table["rows"][0]["date"])


def test_daily_rows_explicit_columns_parse_weights(client: TestClient) -> None:
    sid = _first_scenario(client)
    body = client.get(
        f"/api/v1/backtest-results/{sid}/daily",
        params={"columns": "date,nav,weights", "limit": 3, "offset": 2},
    ).json()
    table = body["table"]
    assert table["columns"] == ["date", "nav", "weights"]
    assert len(table["rows"]) == 3
    # weights parsed from the JSON string back to an object (§6).
    assert isinstance(table["rows"][0]["weights"], dict)


def test_daily_rows_unknown_scenario_404(client: TestClient) -> None:
    resp = client.get("/api/v1/backtest-results/nope/daily")
    assert resp.status_code == 404
