from src.backtest.engine import run_backtest
from src.backtest.portfolio import Portfolio
from src.storage.db_writer import insert_backtest_results, insert_backtest_decision_trace, insert_backtest_regime_trace, insert_volatility_features
from src.storage.db_reader import get_etf_history, get_macro_history
from src.scenarios.factory import build_vol_power_scenarios, build_covariance_scaling_scenarios, build_ewma_covariance_scaling_scenarios, build_legacy_ewma_covariance_scaling_scenarios, build_legacy_covariance_scaling_scenarios
from src.covariance.returns_view import CovarianceReturnsView
from src.volatility import build_volatility_feature_surface, VolatilityFeatureConfig
from src.storage.paths import DB_PATH
import sqlite3
import logging
import pandas as pd

logger = logging.getLogger(__name__)

conn = sqlite3.connect(DB_PATH)

def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.debug("Running backtest. Please be patient...")
    etf_history = get_etf_history()

    macro_history = get_macro_history()

    etf_history = etf_history.dropna(subset=["date"])
    macro_history = macro_history.dropna(subset=["date"])

    required = {"AGG", "SHY", "TLT"}
    available = set(etf_history["ticker"].dropna().unique())
    missing = required - available
    if missing:
        logger.warning("Missing required tickers in ETF history: %s", sorted(missing))
        logger.warning("Available tickers: %s", sorted(available))
        # Fallback to whatever is available for historic coverage, but strategy may be degraded.
        required = required & available

    valid_dates = (
        etf_history
        .groupby("date")["ticker"]
        .apply(lambda s: required.issubset(set(s)))
    )

    etf_start = valid_dates[valid_dates].index.min()

    macro_start = macro_history["date"].min()

    #start_date = max(etf_start, macro_start)
    start_date = max(etf_start, macro_start, pd.Timestamp("2014-01-01"))

    etf_history = etf_history[etf_history["date"] >= start_date]

    tickers = [ticker for ticker in ["TLT", "AGG", "SHY"] if ticker in required]

    returns_view = CovarianceReturnsView.from_etf_history(
        etf_history=etf_history,
        tickers=tickers,
    )

    # Build the volatility feature surface once, shared read-only across all
    # scenarios (scenario-independent, like returns_view).
    volatility_feature_surface = build_volatility_feature_surface(
        etf_history=etf_history,
        tickers=tickers,
        config=VolatilityFeatureConfig(
            rolling_windows=(20, 60),
            ewma_lambdas=(0.94, 0.97),
            include_garch=True,
            garch_refit_frequency="monthly",
            min_history=20,
        ),
        lag_features_days=1,
    )

    # Persist the surface once (scenario-independent): one row per (date, ticker).
    volatility_feature_rows = volatility_feature_surface.values.assign(
        config_key=str(volatility_feature_surface.config.cache_key())
    ).to_dict("records")
    insert_volatility_features(conn, volatility_feature_rows)

    #portfolio = Portfolio(initial_capital=1_000_000)
    #context = run_backtest(etf_history, macro_history, portfolio)

    scenarios = (
        build_vol_power_scenarios()
        +
        build_covariance_scaling_scenarios()
        + 
        build_ewma_covariance_scaling_scenarios()
        + 
        build_legacy_ewma_covariance_scaling_scenarios()
        + 
        build_legacy_covariance_scaling_scenarios()
    )
    
    for scenario in scenarios:
        logger.debug("Running scenario: %s", scenario.scenario_id)

        portfolio = Portfolio(initial_capital=1_000_000)

        context = run_backtest(
            etf_history,
            macro_history,
            portfolio,
            scenario=scenario,
            returns_view=returns_view,
            volatility_feature_surface=volatility_feature_surface,
        )
        for r in context.daily_metrics:
            r["scenario_id"] = scenario.scenario_id

        for r in context.decision_trace:
            r["scenario_id"] = scenario.scenario_id

        for r in context.regime_trace:
            r["scenario_id"] = scenario.scenario_id

        insert_backtest_results(conn, context.daily_metrics)
        insert_backtest_decision_trace(conn, context.decision_trace)
        insert_backtest_regime_trace(conn, context.regime_trace)

    logger.debug("Backtest complete.")
    logger.debug("Covariance cache size: %s", len(returns_view.covariance_cache))
    logger.debug("Covariance cache hits: %s", returns_view.covariance_cache_hits)
    logger.debug("Covariance cache misses: %s", returns_view.covariance_cache_misses)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
