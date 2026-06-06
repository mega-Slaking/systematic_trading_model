"""DB save/load round-trips against a throwaway schema (temp_db fixture).

Covers the writers used by run_backtest and the volatility_features persistence,
including NaN->NULL and INSERT OR REPLACE idempotency.
"""

import sqlite3

import pandas as pd
import pytest

from src.storage import db_reader
from src.storage.db_writer import (
    insert_backtest_results,
    insert_backtest_regime_trace,
    insert_volatility_features,
)

pytestmark = pytest.mark.integration


def _conn(db_path):
    return sqlite3.connect(str(db_path))


def _vol_row(ticker, garch=0.10, date="2020-01-01"):
    return {
        "date": date,
        "ticker": ticker,
        "rolling_20": 0.10,
        "rolling_60": 0.11,
        "ewma_94": 0.09,
        "ewma_97": 0.095,
        "garch": garch,
        "ewma_94_to_rolling_20": 0.9,
        "ewma_94_change_5d": 0.01,
        "ewma_97_to_rolling_20": 0.95,
        "ewma_97_change_5d": 0.02,
        "config_key": "cfg-1",
    }


def test_volatility_features_roundtrip(temp_db, monkeypatch):
    conn = _conn(temp_db)
    insert_volatility_features(conn, [_vol_row("TLT"), _vol_row("AGG")])
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_reader, "DB_PATH", temp_db)
    df = db_reader.get_volatility_features()

    assert len(df) == 2
    assert set(df["ticker"]) == {"TLT", "AGG"}
    tlt = df[df["ticker"] == "TLT"].iloc[0]
    assert tlt["rolling_20"] == pytest.approx(0.10)
    assert tlt["config_key"] == "cfg-1"


def test_volatility_features_nan_becomes_null(temp_db, monkeypatch):
    conn = _conn(temp_db)
    insert_volatility_features(conn, [_vol_row("TLT", garch=float("nan"))])
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_reader, "DB_PATH", temp_db)
    df = db_reader.get_volatility_features()
    assert pd.isna(df.iloc[0]["garch"])  # NaN -> NULL -> NaN on readback


def test_volatility_features_insert_or_replace_is_idempotent(temp_db, monkeypatch):
    conn = _conn(temp_db)
    insert_volatility_features(conn, [_vol_row("TLT", garch=0.10)])
    insert_volatility_features(conn, [_vol_row("TLT", garch=0.20)])  # same PK (date,ticker)
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_reader, "DB_PATH", temp_db)
    df = db_reader.get_volatility_features()
    assert len(df) == 1  # replaced, not duplicated
    assert df.iloc[0]["garch"] == pytest.approx(0.20)  # latest write wins


def test_backtest_regime_trace_roundtrip(temp_db, monkeypatch):
    row = {
        "date": "2020-01-01",
        "scenario_id": "s1",
        "inflation_regime": "DIS",
        "growth_regime": "OK",
        "labour_regime": "OK",
        "curve_state": "NORM",
        "macro_supports_duration": True,
    }
    conn = _conn(temp_db)
    insert_backtest_regime_trace(conn, [row])
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_reader, "DB_PATH", temp_db)
    df = db_reader.get_backtest_regime_trace(scenario_id="s1")

    assert len(df) == 1
    assert df.iloc[0]["inflation_regime"] == "DIS"
    # writer stores the bool as int(1)
    assert int(df.iloc[0]["macro_supports_duration"]) == 1


def test_backtest_results_write_readback_raw(temp_db):
    row = {
        "date": "2020-01-01",
        "scenario_id": "s1",
        "nav_pre": 1000.0,
        "nav": 1010.0,
        "ret": 0.01,
        "turnover": 0.1,
        "fee_cost": 0.0,
        "slippage_cost": 0.0,
        "total_cost": 0.0,
        "gross_trade_notional": 500.0,
        "weights": {"TLT": 0.6, "AGG": 0.4},
        "n_positions": 2,
        "top_asset": "TLT",
        "top_weight": 0.6,
    }
    conn = _conn(temp_db)
    insert_backtest_results(conn, [row])
    conn.commit()

    cur = conn.execute(
        "SELECT nav, gross_trade_notional, weights, top_asset FROM backtest_results WHERE date=?",
        ("2020-01-01",),
    )
    nav, gross, weights_json, top_asset = cur.fetchone()
    conn.close()

    assert nav == pytest.approx(1010.0)
    assert gross == pytest.approx(500.0)
    assert top_asset == "TLT"
    assert '"TLT"' in weights_json  # dict serialized to JSON


def test_backtest_results_roundtrip_via_reader(temp_db, monkeypatch):
    # Regression guard for the gross_notional -> gross_trade_notional column fix.
    row = {
        "date": "2020-01-01",
        "scenario_id": "s1",
        "nav_pre": 1000.0,
        "nav": 1010.0,
        "ret": 0.01,
        "turnover": 0.1,
        "fee_cost": 0.0,
        "slippage_cost": 0.0,
        "total_cost": 0.0,
        "gross_trade_notional": 500.0,
        "weights": {"TLT": 0.6, "AGG": 0.4},
        "n_positions": 2,
        "top_asset": "TLT",
        "top_weight": 0.6,
    }
    conn = _conn(temp_db)
    insert_backtest_results(conn, [row])
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_reader, "DB_PATH", temp_db)
    df = db_reader.get_backtest_results(scenario_id="s1")

    assert len(df) == 1
    assert "gross_trade_notional" in df.columns
    assert df.iloc[0]["gross_trade_notional"] == pytest.approx(500.0)
    assert df.iloc[0]["nav"] == pytest.approx(1010.0)
