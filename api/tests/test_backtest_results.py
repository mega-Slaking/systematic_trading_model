"""Tests for the NAV-comparison + returns endpoints (2 + 3) and their reducers.

Endpoint tests run against the populated repo DB; the reducer tests
(``nav_summary_rows`` / ``buy_and_hold_nav``) are DB-independent.
"""

from __future__ import annotations

import json
import re

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.services import summaries

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _scenarios(client: TestClient) -> list[str]:
    return client.get("/api/v1/scenarios").json()["scenarios"]


# --------------------------------------------------------------------------- #
# Endpoint 2: /backtest-results/nav-comparison
# --------------------------------------------------------------------------- #
def test_nav_comparison_shape(client: TestClient) -> None:
    resp = client.get("/api/v1/backtest-results/nav-comparison")
    assert resp.status_code == 200
    body = resp.json()
    scenarios = _scenarios(client)

    assert len(body["scenario_series"]) == len(scenarios)
    for s in body["scenario_series"]:
        assert s["name"].startswith("Scenario: ")
        assert s["points"]

    assert 1 <= len(body["benchmark_series"]) <= 3
    for b in body["benchmark_series"]:
        assert b["name"].startswith("B&H: ")
        assert b["meta"] == {"dash": "dash"}  # dashed lines (§4.4)

    assert body["initial_nav"] > 0
    assert _ISO_DATE.match(body["start_date"])
    # Summary: one row per scenario, in sorted order.
    assert [r["scenario_id"] for r in body["summary"]] == sorted(scenarios)


def test_nav_comparison_filters_scenarios(client: TestClient) -> None:
    one = _scenarios(client)[0]
    body = client.get(
        "/api/v1/backtest-results/nav-comparison", params={"scenario_ids": one}
    ).json()
    assert [s["name"] for s in body["scenario_series"]] == [f"Scenario: {one}"]
    assert [r["scenario_id"] for r in body["summary"]] == [one]


def test_nav_comparison_filters_benchmarks(client: TestClient) -> None:
    body = client.get(
        "/api/v1/backtest-results/nav-comparison", params={"benchmarks": "tlt"}
    ).json()
    assert [b["name"] for b in body["benchmark_series"]] == ["B&H: TLT"]


# --------------------------------------------------------------------------- #
# Endpoint 3: /backtest-results/returns
# --------------------------------------------------------------------------- #
def test_returns_columnar_shape(client: TestClient) -> None:
    resp = client.get("/api/v1/backtest-results/returns")
    assert resp.status_code == 200
    series = resp.json()["series"]
    assert [s["scenario_id"] for s in series] == sorted(_scenarios(client))
    for s in series:
        assert len(s["dates"]) == len(s["returns"])  # columnar, parallel arrays
        assert s["dates"], f"{s['scenario_id']} has no dates"
        assert _ISO_DATE.match(s["dates"][0])


def test_returns_filter_single_scenario(client: TestClient) -> None:
    one = _scenarios(client)[0]
    series = client.get(
        "/api/v1/backtest-results/returns", params={"scenario_ids": one}
    ).json()["series"]
    assert [s["scenario_id"] for s in series] == [one]


def test_phase2_endpoints_emit_strict_json(client: TestClient) -> None:
    """§6/§10.3 guard: no raw NaN/Infinity tokens leak into the JSON."""
    for path in (
        "/api/v1/scenarios",
        "/api/v1/backtest-results/nav-comparison",
        "/api/v1/backtest-results/returns",
    ):
        text = client.get(path).text
        assert "NaN" not in text and "Infinity" not in text, path
        json.loads(text)


# --------------------------------------------------------------------------- #
# Reducer unit tests (DB-independent)
# --------------------------------------------------------------------------- #
def _bt_frame() -> pd.DataFrame:
    rows = [
        ("2020-01-01", "A", 100.0, 0.0),
        ("2020-01-02", "A", 120.0, 0.20),
        ("2020-01-03", "A", 90.0, -0.25),
        ("2020-01-01", "B", 50.0, 0.0),
        ("2020-01-02", "B", 55.0, 0.10),
    ]
    return pd.DataFrame(
        [{"date": d, "scenario_id": s, "nav": n, "ret": r} for d, s, n, r in rows]
    ).assign(date=lambda df: pd.to_datetime(df["date"]))


def test_nav_summary_rows_reproduces_streamlit_math() -> None:
    rows = summaries.nav_summary_rows(_bt_frame())
    assert [r.scenario_id for r in rows] == ["A", "B"]  # sorted

    a = rows[0]
    assert a.final_nav == 90.0
    assert a.total_return == pytest.approx(90.0 / 100.0 - 1.0)  # -0.10
    # peak = [100,120,120]; drawdown min = 90/120 - 1 = -0.25
    assert a.max_drawdown == pytest.approx(-0.25)
    # vol = sample std of returns * sqrt(252) (ddof=1, matching nav_comparison.py)
    expected_vol = pd.Series([0.0, 0.20, -0.25]).std() * (252**0.5)
    assert a.annualized_volatility == pytest.approx(expected_vol)


def test_nav_summary_rows_skips_when_ret_absent() -> None:
    frame = _bt_frame().drop(columns=["ret"])
    rows = summaries.nav_summary_rows(frame)
    assert all(r.annualized_volatility is None for r in rows)


def test_buy_and_hold_nav_scales_from_first_close() -> None:
    prices = pd.DataFrame(
        {"date": pd.to_datetime(["2020-01-01", "2020-01-02"]), "close": [10.0, 11.0]}
    )
    out = summaries.buy_and_hold_nav(prices, 1000.0)  # 100 shares
    assert list(out["nav"]) == [1000.0, 1100.0]


def test_buy_and_hold_nav_degenerate_first_close_is_nan_not_inf() -> None:
    prices = pd.DataFrame(
        {"date": pd.to_datetime(["2020-01-01", "2020-01-02"]), "close": [0.0, 5.0]}
    )
    out = summaries.buy_and_hold_nav(prices, 1000.0)
    assert out["nav"].isna().all()  # -> null points, never Inf
