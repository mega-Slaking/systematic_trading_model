import sqlite3


def create_tables(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executescript("""
        DROP TABLE IF EXISTS decision_trace;
        DROP TABLE IF EXISTS regime_trace;
        DROP TABLE IF EXISTS etf_prices;
        DROP TABLE IF EXISTS macro_data;
        DROP TABLE IF EXISTS backtest_results;
        DROP TABLE IF EXISTS backtest_decision_trace;
        DROP TABLE IF EXISTS backtest_regime_trace;
        DROP TABLE IF EXISTS volatility_features;
        """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS decision_trace (
        date TEXT PRIMARY KEY,
        disinflation TEXT ,
        curve_inverted TEXT ,
        growth_slowing TEXT ,
        labour_weakening TEXT ,
        tlt_pos REAL ,
        agg_pos REAL ,
        shy_pos REAL 
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS regime_trace (
        date TEXT PRIMARY KEY,
        inflation_regime TEXT ,
        growth_regime TEXT ,
        labour_regime TEXT ,
        curve_state TEXT ,
        macro_supports_duration TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS etf_prices (
        date TEXT NOT NULL,
        ticker TEXT NOT NULL,
        close REAL,
        PRIMARY KEY(date, ticker)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS macro_data (
        date TEXT PRIMARY KEY,

        cpi REAL,
        core_cpi REAL,
        unemployment REAL,
        payrolls REAL,

        gs2 REAL,
        gs10 REAL,
        pmi REAL,

        fed_funds REAL,
        hy_oas REAL,
        consumer_sentiment REAL,
        jobless_claims REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS backtest_results (
        date TEXT,
        scenario_id TEXT,
        nav_pre REAL ,
        nav REAL ,
        ret REAL ,
        turnover REAL ,
        fee_cost REAL ,
        slippage_cost REAL,
        total_cost REAL ,
        gross_trade_notional REAL,
        weights TEXT,
        n_positions INTEGER,
        top_asset TEXT,
        top_weight REAL,
        PRIMARY KEY (date, scenario_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS backtest_decision_trace (
        date TEXT,
        scenario_id TEXT,
        disinflation TEXT ,
        curve_inverted TEXT ,
        growth_slowing TEXT ,
        labour_weakening TEXT ,
        top_asset TEXT,
        w_tlt REAL ,
        w_agg REAL ,
        w_shy REAL,
        PRIMARY KEY (date, scenario_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS backtest_regime_trace (
        date TEXT,
        scenario_id TEXT,
        inflation_regime TEXT ,
        growth_regime TEXT ,
        labour_regime TEXT ,
        curve_state TEXT ,
        macro_supports_duration TEXT,
        PRIMARY KEY (date, scenario_id)
    )
    """)
    #I know this is identical to another table but for simplicity I have it separated

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS volatility_features (
        date TEXT,
        ticker TEXT,
        rolling_20 REAL,
        rolling_60 REAL,
        ewma_94 REAL,
        ewma_97 REAL,
        garch REAL,
        ewma_94_to_rolling_20 REAL,
        ewma_94_change_5d REAL,
        ewma_97_to_rolling_20 REAL,
        ewma_97_change_5d REAL,
        config_key TEXT,
        PRIMARY KEY (date, ticker)
    )
    """)
    #Scenario-independent: one row per (date, ticker), shared across all scenarios.

    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_tables("data/database.db")