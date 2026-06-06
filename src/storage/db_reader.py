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


def get_backtest_regime_trace(scenario_id: str | None = None) -> pd.DataFrame:
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
    """

    params = {}

    if scenario_id is not None:
        query += """
            WHERE scenario_id = :scenario_id
        """
        params["scenario_id"] = scenario_id

    query += """
        ORDER BY scenario_id, date
    """

    with _connect() as conn:
        df = pd.read_sql(
            query,
            conn,
            params=params,
            parse_dates=["date"],
        )

    return df


def get_scenario_ids() -> list[str]:
    query = """
        SELECT DISTINCT scenario_id
        FROM backtest_results
        ORDER BY scenario_id
    """

    with _connect() as conn:
        df = pd.read_sql(query, conn)

    return df["scenario_id"].tolist()
#This way, we only query scenarios we want rather than everything


def get_volatility_features(tickers=None) -> pd.DataFrame:
    query = """
        SELECT
            date,
            ticker,
            rolling_20,
            rolling_60,
            ewma_94,
            ewma_97,
            garch,
            ewma_94_to_rolling_20,
            ewma_94_change_5d,
            ewma_97_to_rolling_20,
            ewma_97_change_5d,
            config_key
        FROM volatility_features
    """

    params = []

    if tickers:
        placeholders = ",".join("?" for _ in tickers)
        query += f" WHERE ticker IN ({placeholders})"
        params.extend(tickers)

    query += " ORDER BY ticker, date"

    with _connect() as conn:
        df = pd.read_sql(query, conn, params=params, parse_dates=["date"])

    return df


def get_backtest_results(scenario_id: str | None = None) -> pd.DataFrame:
    base_query = """
        SELECT
            date,
            scenario_id,
            nav_pre,
            nav,
            ret,
            turnover,
            fee_cost,
            slippage_cost,
            total_cost,
            gross_notional,
            weights,
            n_positions,
            top_asset,
            top_weight
        FROM backtest_results
    """

    params = {}

    if scenario_id is not None:
        base_query += """
            WHERE scenario_id = :scenario_id
        """
        params["scenario_id"] = scenario_id

    base_query += """
        ORDER BY scenario_id, date
    """

    with _connect() as conn:
        df = pd.read_sql(
            base_query,
            conn,
            params=params,
            parse_dates=["date"],
        )

    return df