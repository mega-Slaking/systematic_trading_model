import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path("data/database.db")


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def get_etf_history(tickers=None):
    query = """
        SELECT date, close, ticker
        FROM etf_prices
    """
    params = []

    if tickers:
        placeholders = ",".join("?" for _ in tickers)
        query += f" WHERE ticker IN ({placeholders})"
        params.extend(tickers)

    query += " ORDER BY ticker, date"

    with _connect() as conn:
        df = pd.read_sql(query, conn, params=params, parse_dates=["date"])

    # Ensure correct column names and dtypes
    df = df[['date', 'close', 'ticker']].copy()  # Reorder explicitly
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    
    return df


def get_macro_history():
    query = """
        SELECT
            date,
            cpi,
            core_cpi,
            unemployment,
            payrolls,
            gs2,
            gs10,
            pmi,
            fed_funds,
            hy_oas,
            consumer_sentiment,
            jobless_claims
        FROM macro_data
        ORDER BY date
    """

    with _connect() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])

    return df


def get_backtest_regime_trace():
    query = """
        SELECT date, inflation_regime, growth_regime, 
        labour_regime, curve_state, macro_supports_duration
        FROM regime_trace
        ORDER BY date
    """

    with _connect() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])

    return df
