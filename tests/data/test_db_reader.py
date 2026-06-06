"""Price loading via db_reader against a throwaway DB (no live database touched)."""

import sqlite3

import pytest

from src.storage import db_reader

pytestmark = pytest.mark.integration


def _seed_prices(db_path, rows):
    conn = sqlite3.connect(str(db_path))
    conn.executemany(
        "INSERT INTO etf_prices (date, ticker, close) VALUES (?, ?, ?)", rows
    )
    conn.commit()
    conn.close()


def test_get_etf_history_loads_expected_rows(temp_db, monkeypatch):
    _seed_prices(
        temp_db,
        [
            ("2020-01-01", "TLT", 100.0),
            ("2020-01-02", "TLT", 101.0),
            ("2020-01-01", "AGG", 50.0),
        ],
    )
    monkeypatch.setattr(db_reader, "DB_PATH", temp_db)

    df = db_reader.get_etf_history()

    assert set(df.columns) == {"date", "close", "ticker"}
    assert len(df) == 3
    assert df[df["ticker"] == "TLT"].shape[0] == 2


def test_get_etf_history_filters_by_ticker(temp_db, monkeypatch):
    _seed_prices(
        temp_db,
        [
            ("2020-01-01", "TLT", 100.0),
            ("2020-01-01", "AGG", 50.0),
            ("2020-01-01", "SHY", 80.0),
        ],
    )
    monkeypatch.setattr(db_reader, "DB_PATH", temp_db)

    df = db_reader.get_etf_history(tickers=["TLT", "SHY"])

    assert set(df["ticker"].unique()) == {"TLT", "SHY"}


def test_get_etf_history_empty_table_returns_empty_frame(temp_db, monkeypatch):
    monkeypatch.setattr(db_reader, "DB_PATH", temp_db)
    df = db_reader.get_etf_history()
    assert df.empty
    assert set(df.columns) == {"date", "close", "ticker"}
