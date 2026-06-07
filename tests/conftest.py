"""Shared fixtures for the test suite."""

import sqlite3

import numpy as np
import pandas as pd
import pytest


# Self-contained schema for the tables the suite exercises. Mirrors
# data/db_population.py, but inlined so tests don't depend on that file (which is
# gitignored and therefore absent in a fresh CI checkout).
_TEST_SCHEMA = """
CREATE TABLE IF NOT EXISTS etf_prices (
    date TEXT NOT NULL, ticker TEXT NOT NULL, close REAL,
    PRIMARY KEY(date, ticker)
);
CREATE TABLE IF NOT EXISTS backtest_results (
    date TEXT, scenario_id TEXT, nav_pre REAL, nav REAL, ret REAL, turnover REAL,
    fee_cost REAL, slippage_cost REAL, total_cost REAL, gross_trade_notional REAL,
    weights TEXT, n_positions INTEGER, top_asset TEXT, top_weight REAL,
    PRIMARY KEY (date, scenario_id)
);
CREATE TABLE IF NOT EXISTS backtest_regime_trace (
    date TEXT, scenario_id TEXT, inflation_regime TEXT, growth_regime TEXT,
    labour_regime TEXT, curve_state TEXT, macro_supports_duration TEXT,
    PRIMARY KEY (date, scenario_id)
);
CREATE TABLE IF NOT EXISTS volatility_features (
    date TEXT, ticker TEXT, rolling_20 REAL, rolling_60 REAL, ewma_94 REAL,
    ewma_97 REAL, garch REAL, ewma_94_to_rolling_20 REAL, ewma_94_change_5d REAL,
    ewma_97_to_rolling_20 REAL, ewma_97_change_5d REAL, config_key TEXT,
    PRIMARY KEY (date, ticker)
);
"""


@pytest.fixture
def synthetic_etf_history():
    """Deterministic seeded (date, ticker, close) for TLT/AGG/SHY over 200 bdays.

    Vols are tiered TLT > AGG > SHY to mimic the real duration ordering.
    """
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2020-01-01", periods=200)
    params = {"TLT": (0.0002, 0.010), "AGG": (0.0001, 0.004), "SHY": (0.00005, 0.0012)}
    rows = []
    for ticker, (mu, sigma) in params.items():
        rets = rng.normal(mu, sigma, len(dates))
        prices = 100.0 * np.cumprod(1.0 + rets)
        rows.extend(
            {"date": d, "ticker": ticker, "close": float(p)}
            for d, p in zip(dates, prices)
        )
    return pd.DataFrame(rows)


@pytest.fixture
def synthetic_macro_history():
    """Deterministic monthly macro frame matching the macro_data schema (30 months)."""
    rng = np.random.default_rng(7)
    dates = pd.date_range("2018-01-01", periods=30, freq="MS")
    n = len(dates)
    return pd.DataFrame(
        {
            "date": dates,
            "cpi": 250 + np.cumsum(rng.normal(0.3, 0.2, n)),
            "core_cpi": 255 + np.cumsum(rng.normal(0.3, 0.15, n)),
            "unemployment": 4.0 + np.cumsum(rng.normal(0.0, 0.05, n)),
            "payrolls": 150000 + np.cumsum(rng.normal(100, 50, n)),
            "gs2": 2.0 + np.cumsum(rng.normal(0.0, 0.05, n)),
            "gs10": 3.0 + np.cumsum(rng.normal(0.0, 0.05, n)),
            "pmi": rng.normal(0.1, 0.3, n),
            "fed_funds": 1.5 + np.cumsum(rng.normal(0.0, 0.03, n)),
            "hy_oas": 4.0 + np.cumsum(rng.normal(0.0, 0.1, n)),
            "consumer_sentiment": 95 + np.cumsum(rng.normal(0.0, 1.0, n)),
            "jobless_claims": 220000 + np.cumsum(rng.normal(0, 2000, n)),
        }
    )


@pytest.fixture
def sample_prices():
    return {"TLT": 100.0, "AGG": 50.0, "SHY": 80.0}


@pytest.fixture
def make_macro_signals():
    """Factory: a one-row macro_signals frame with overridable regime flags."""
    def _make(**flags):
        row = dict(
            date=pd.Timestamp("2020-06-01"),
            cpi_yoy=0.02,
            core_cpi_yoy=0.02,
            disinflation=False,
            inflation_rising=False,
            growth_slowing=False,
            labor_weakening=False,
            jobless_rising=False,
            curve_inverted=False,
            real_rate_tight=False,
            credit_spread_widening=False,
            confidence_low=False,
            macro_supports_duration=False,
            fed_funds_direction=0.0,
        )
        row.update(flags)
        return pd.DataFrame([row])

    return _make


@pytest.fixture
def make_price_signals():
    """Factory: a price_signals frame (one row per ticker)."""
    def _make(ret=0.01, trend_up=True, ma_slope_z=0.5, tickers=("TLT", "AGG", "SHY")):
        return pd.DataFrame(
            [
                dict(
                    date=pd.Timestamp("2020-06-01"),
                    ticker=t,
                    ret_lookback=ret,
                    trend_up=trend_up,
                    ma_slope_z=ma_slope_z,
                )
                for t in tickers
            ]
        )

    return _make


@pytest.fixture
def temp_db(tmp_path):
    """Throwaway sqlite with the test schema. Never touches data/database.db."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_TEST_SCHEMA)
    conn.commit()
    conn.close()
    return db_path
