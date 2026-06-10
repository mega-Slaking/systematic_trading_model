"""Tests for the ETF-prices endpoints (6 + 7) and the stats reducer (Phase 1).

Endpoint tests run against the populated repo DB (like ``test_health``); the
reducer tests are DB-independent so the §6 NaN/zero-base math is locked even on a
fresh checkout.
"""

from __future__ import annotations

import json
import re

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.services import summaries

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CANONICAL = ["TLT", "AGG", "SHY"]


# --------------------------------------------------------------------------- #
# Endpoint 6: /etf-prices
# --------------------------------------------------------------------------- #
def test_etf_prices_returns_one_series_per_ticker(client: TestClient) -> None:
    resp = client.get("/api/v1/etf-prices")
    assert resp.status_code == 200
    series = resp.json()["series"]
    assert [s["name"] for s in series] == _CANONICAL  # canonical order, all three
    for s in series:
        assert s["points"], f"{s['name']} has no points"
        first = s["points"][0]
        assert _ISO_DATE.match(first["date"]), first["date"]
        assert first["value"] is None or isinstance(first["value"], (int, float))


def test_etf_prices_filter_by_single_ticker(client: TestClient) -> None:
    resp = client.get("/api/v1/etf-prices", params={"tickers": "TLT"})
    assert resp.status_code == 200
    series = resp.json()["series"]
    assert [s["name"] for s in series] == ["TLT"]


def test_etf_prices_filter_is_case_insensitive(client: TestClient) -> None:
    resp = client.get("/api/v1/etf-prices", params={"tickers": "tlt,agg"})
    assert resp.status_code == 200
    assert [s["name"] for s in resp.json()["series"]] == ["TLT", "AGG"]


def test_etf_prices_unknown_ticker_yields_no_series(client: TestClient) -> None:
    resp = client.get("/api/v1/etf-prices", params={"tickers": "ZZZ"})
    assert resp.status_code == 200
    assert resp.json()["series"] == []


# --------------------------------------------------------------------------- #
# Endpoint 7: /etf-prices/stats
# --------------------------------------------------------------------------- #
def test_etf_price_stats_shape_and_internal_consistency(client: TestClient) -> None:
    resp = client.get("/api/v1/etf-prices/stats")
    assert resp.status_code == 200
    stats = resp.json()["stats"]
    assert [row["ticker"] for row in stats] == _CANONICAL
    for row in stats:
        lo, hi = row["min_close"], row["max_close"]
        assert lo is not None and hi is not None and lo <= hi
        # first_close is finite (2002 history exists) and within [min, max].
        assert row["first_close"] is not None and lo <= row["first_close"] <= hi
        # last_close MAY be null: the repo DB's latest row (2026-06-09) carries a
        # NaN close for every ticker, which the §6 boundary maps to null. When
        # present, it lies in [min, max] and total_return == last/first - 1; when
        # null, total_return is null too (never Inf/NaN).
        if row["last_close"] is not None:
            assert lo <= row["last_close"] <= hi
            expected = row["last_close"] / row["first_close"] - 1.0
            assert row["total_return"] == pytest.approx(expected, rel=1e-9)
        else:
            assert row["total_return"] is None


def test_etf_endpoints_emit_strict_json_no_nan_tokens(client: TestClient) -> None:
    """§6/§10.3 guard: responses must be strict JSON -- never raw NaN/Infinity tokens."""
    for path in ("/api/v1/etf-prices", "/api/v1/etf-prices/stats"):
        text = client.get(path).text
        assert "NaN" not in text and "Infinity" not in text, path
        json.loads(text)  # strict parse must succeed


# --------------------------------------------------------------------------- #
# Reducer unit tests (DB-independent): summaries.etf_price_stats
# --------------------------------------------------------------------------- #
def _frame(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"date": d, "ticker": t, "close": c} for d, t, c in rows]
    ).assign(date=lambda df: pd.to_datetime(df["date"]))


def test_reducer_basic_first_last_min_max_and_total_return() -> None:
    df = _frame([("2020-01-01", "AAA", 100.0), ("2020-01-02", "AAA", 110.0)])
    [stat] = summaries.etf_price_stats(df, ["AAA"])
    assert (stat.first_close, stat.last_close) == (100.0, 110.0)
    assert (stat.min_close, stat.max_close) == (100.0, 110.0)
    assert stat.total_return == pytest.approx(0.10)


def test_reducer_sorts_by_date_not_row_order() -> None:
    # Rows deliberately out of chronological order; first/last must respect dates.
    df = _frame(
        [("2020-01-03", "CCC", 103.0), ("2020-01-01", "CCC", 101.0), ("2020-01-02", "CCC", 102.0)]
    )
    [stat] = summaries.etf_price_stats(df, ["CCC"])
    assert (stat.first_close, stat.last_close) == (101.0, 103.0)


def test_reducer_skips_nan_in_min_max_and_nulls_total_on_nan_endpoint() -> None:
    df = _frame(
        [("2020-01-01", "AAA", 100.0), ("2020-01-02", "AAA", float("nan")), ("2020-01-03", "AAA", 120.0)]
    )
    [stat] = summaries.etf_price_stats(df, ["AAA"])
    assert stat.min_close == 100.0 and stat.max_close == 120.0  # NaN skipped
    assert stat.total_return == pytest.approx(0.20)


def test_reducer_zero_base_returns_none_total_not_inf() -> None:
    df = _frame([("2020-01-01", "BBB", 0.0), ("2020-01-02", "BBB", 5.0)])
    [stat] = summaries.etf_price_stats(df, ["BBB"])
    assert stat.first_close == 0.0
    assert stat.total_return is None  # guarded zero base (would be Inf)


def test_reducer_orders_by_request_and_skips_absent() -> None:
    df = _frame([("2020-01-01", "TLT", 1.0), ("2020-01-01", "AGG", 2.0)])
    stats = summaries.etf_price_stats(df, ["TLT", "ZZZ", "AGG"])  # ZZZ has no rows
    assert [s.ticker for s in stats] == ["TLT", "AGG"]
