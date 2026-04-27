import sqlite3
import json

def _json_if_dict(v):
    if isinstance(v, dict):
        return json.dumps(v)
    return v

def _sql_date(var):
    if var is None:
        return None
    if hasattr(var, "strftime"):
        return var.strftime("%Y-%m-%d")
    return var


def insert_decision_trace(conn: sqlite3.Connection, rows: list[dict]) -> None:

    payload = [
        (
            _sql_date(r.get("date")),
            r.get("disinflation"),
            r.get("curve_inverted"),
            r.get("growth_slowing"),
            r.get("labour_weakening"),
            r.get("tlt_pos"),
            r.get("agg_pos"),
            r.get("shy_pos"),
        )
        for r in rows
    ]

    conn.executemany(
        """
        INSERT OR REPLACE INTO decision_trace VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )


def insert_regime_trace(conn: sqlite3.Connection, rows: list[dict]) -> None:

    payload = [
        (
            _sql_date(r.get("date")),
            r.get("inflation_regime"),
            r.get("growth_regime"),
            r.get("labour_regime"),
            r.get("curve_state"),
            r.get("macro_supports_duration"),
        )
        for r in rows
    ]

    conn.executemany(
        """
        INSERT OR REPLACE INTO regime_trace VALUES (?, ?, ?, ?, ?, ?)
        """,
        payload,
    )


def insert_etf_prices(conn: sqlite3.Connection, rows: list[dict]) -> None:

    payload = [
        (
            _sql_date(r.get("date")),
            r.get("ticker"),
            r.get("close"),
        )
        for r in rows
    ]

    conn.executemany(
        """
        INSERT OR REPLACE INTO etf_prices (date, ticker, close) VALUES (?, ?, ?)
        """,
        payload,
    )


def insert_macro_data(conn: sqlite3.Connection, rows: list[dict]) -> None:

    payload = [
        (
            _sql_date(r.get("date")),
            r.get("cpi"),
            r.get("core_cpi"),
            r.get("unemployment"),
            r.get("payrolls"),
            r.get("gs2"),
            r.get("gs10"),
            r.get("pmi"),
            r.get("fed_funds"),
            r.get("hy_oas"),
            r.get("consumer_sentiment"),
            r.get("jobless_claims"),
        )
        for r in rows
    ]

    conn.executemany(
        """
        INSERT OR REPLACE INTO macro_data (
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
        )
        VALUES (
            ?,?,?,?,?,?,
            ?,?,?,?,?,?
        )
        """,
        payload,
    )
    #explicit inserts are probably safer now as I may add more things


def insert_backtest_results(conn: sqlite3.Connection, rows: list[dict]) -> None:

    payload = [
        (
            _sql_date(r.get("date")),
            r.get("scenario_id"),
            r.get("nav_pre"),
            r.get("nav"),
            r.get("ret"),
            r.get("turnover"),
            r.get("fee_cost"),
            r.get("slippage_cost"),
            r.get("total_cost"),
            r.get("gross_trade_notional"),
            _json_if_dict(r.get("weights")),
            r.get("n_positions"),
            r.get("top_asset"),
            r.get("top_weight"),
        )
        for r in rows
    ]

    conn.executemany(
        """
        INSERT OR REPLACE INTO backtest_results VALUES (
        ?,?,?,?,?,?,?,?,?,?,
        ?,?,?,?
        )
        """,
        payload,
    )


def insert_backtest_decision_trace(conn: sqlite3.Connection, rows: list[dict]) -> None:

    payload = [
        (
            _sql_date(r.get("date")),
            r.get("scenario_id"),
            r.get("disinflation"),
            r.get("curve_inverted"),
            r.get("growth_slowing"),
            r.get("labor_weakening"),
            r.get("chosen_asset"),
            r.get("w_TLT"),
            r.get("w_AGG"),
            r.get("w_SHY"),
        )
        for r in rows
    ]

    conn.executemany(
        """
        INSERT OR REPLACE INTO backtest_decision_trace VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )

def insert_backtest_regime_trace(conn: sqlite3.Connection, rows: list[dict]) -> None:

    payload = [
        (
            _sql_date(r.get("date")),
            r.get("scenario_id"),
            r.get("inflation_regime"),
            r.get("growth_regime"),
            r.get("labour_regime"),
            r.get("curve_state"),
            int(bool(r.get("macro_supports_duration"))) if r.get("macro_supports_duration") is not None else None,
        )
        for r in rows
    ]

    conn.executemany(
        """
        INSERT OR REPLACE INTO backtest_regime_trace VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )