"""Shared utilities for home page tabs."""

import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "database.db"


def connect_db() -> sqlite3.Connection:
    """Create a database connection."""
    return sqlite3.connect(DB_PATH)


@st.cache_data
def load_backtest_results() -> pd.DataFrame:
    """Load backtest results from database."""
    query = "SELECT * FROM backtest_results ORDER BY scenario_id, date"
    with connect_db() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])

    return df


@st.cache_data
def load_etf_prices() -> pd.DataFrame:
    """Load ETF prices from database."""
    query = "SELECT date, ticker, close FROM etf_prices ORDER BY ticker, date"
    with connect_db() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])

    return df


@st.cache_data
def load_regime_trace() -> pd.DataFrame:
    """Load regime trace from database."""
    query = """
        SELECT
            date,
            scenario_id,
            inflation_regime,
            growth_regime,
            labour_regime,
            curve_state,
            macro_supports_duration
        FROM backtest_regime_trace
        ORDER BY scenario_id, date
    """

    with connect_db() as conn:
        df = pd.read_sql(query, conn, parse_dates=["date"])

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])

    return df
