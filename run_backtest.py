from src.backtest.engine import run_backtest
from src.backtest.portfolio import Portfolio
from src.storage.db_writer import insert_backtest_results, insert_backtest_decision_trace, insert_backtest_regime_trace, insert_volatility_features
from src.storage.db_reader import get_etf_history, get_macro_history
# --- OLD scenario-builder imports (commented out per project convention;
# --- replaced by the STRATEGIES registry). Kept as a rollback safety net.
# from src.scenarios.factory import build_vol_power_scenarios, build_covariance_scaling_scenarios, build_ewma_covariance_scaling_scenarios, build_legacy_ewma_covariance_scaling_scenarios, build_legacy_covariance_scaling_scenarios
from src.strategy.presets import STRATEGIES
from src.covariance.returns_view import CovarianceReturnsView
from src.volatility import build_volatility_feature_surface, VolatilityFeatureConfig
from src.storage.paths import DB_PATH
import sqlite3
import logging
import pandas as pd

logger = logging.getLogger(__name__)

# Module-level connection removed: the DB connection is now opened per-run inside
# run_backtests() so the engine can be triggered repeatedly (e.g. by the analytics
# API job endpoint) instead of once per process. Kept commented per convention.
# conn = sqlite3.connect(DB_PATH)


def run_backtests(strategy_names: list[str] | None = None) -> list[str]:
    """Run + persist the backtest for the selected strategies; return the written ids.

    This is main()'s former body, extracted into a callable so the analytics API
    can trigger a run (the single prerequisite for the backtest-from-UI job, spec
    §5.1). Behaviour is identical to the previous ``main()`` when called with no
    arguments (all strategies); the only change is that the DB connection is opened
    here per-run rather than once at module import. ``strategy_names`` (a subset of
    ``STRATEGIES`` keys) restricts the run; ``None`` runs the whole registry.
    """
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
    start_date = max(etf_start, macro_start, pd.Timestamp("2010-01-01"))

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

    # Build the (scenario-independent) volatility surface rows once; persisted below.
    volatility_feature_rows = volatility_feature_surface.values.assign(
        config_key=str(volatility_feature_surface.config.cache_key())
    ).to_dict("records")

    # Select the strategies to run: an explicit subset (validated by the caller) or
    # the whole registry by default.
    selected = (
        [STRATEGIES[name] for name in strategy_names]
        if strategy_names
        else list(STRATEGIES.values())
    )

    #portfolio = Portfolio(initial_capital=1_000_000)
    #context = run_backtest(etf_history, macro_history, portfolio)

    # --- OLD scenario list (commented out per project convention; replaced by
    # --- iterating the STRATEGIES registry). Kept as a rollback safety net.
    # scenarios = (
    #     build_vol_power_scenarios()
    #     +
    #     build_covariance_scaling_scenarios()
    #     +
    #     build_ewma_covariance_scaling_scenarios()
    #     +
    #     build_legacy_ewma_covariance_scaling_scenarios()
    #     +
    #     build_legacy_covariance_scaling_scenarios()
    # )
    #
    # for scenario in scenarios:
    #     logger.debug("Running scenario: %s", scenario.scenario_id)
    #
    #     portfolio = Portfolio(initial_capital=1_000_000)
    #
    #     context = run_backtest(
    #         etf_history,
    #         macro_history,
    #         portfolio,
    #         scenario=scenario,
    #         returns_view=returns_view,
    #         volatility_feature_surface=volatility_feature_surface,
    #     )
    #     for r in context.daily_metrics:
    #         r["scenario_id"] = scenario.scenario_id
    #
    #     for r in context.decision_trace:
    #         r["scenario_id"] = scenario.scenario_id
    #
    #     for r in context.regime_trace:
    #         r["scenario_id"] = scenario.scenario_id
    #
    #     insert_backtest_results(conn, context.daily_metrics)
    #     insert_backtest_decision_trace(conn, context.decision_trace)
    #     insert_backtest_regime_trace(conn, context.regime_trace)

    written: list[str] = []
    conn = sqlite3.connect(DB_PATH)
    try:
        # Persist the (scenario-independent) volatility surface once per run.
        insert_volatility_features(conn, volatility_feature_rows)

        for strategy in selected:
            logger.debug("Running strategy: %s", strategy.name)

            portfolio = Portfolio(initial_capital=1_000_000)

            context = run_backtest(
                etf_history,
                macro_history,
                portfolio,
                strategy=strategy,
                returns_view=returns_view,
                volatility_feature_surface=volatility_feature_surface,
            )
            # strategy.name now plays the scenario_id role (the DB column/key is unchanged).
            for r in context.daily_metrics:
                r["scenario_id"] = strategy.name

            for r in context.decision_trace:
                r["scenario_id"] = strategy.name

            for r in context.regime_trace:
                r["scenario_id"] = strategy.name

            insert_backtest_results(conn, context.daily_metrics)
            insert_backtest_decision_trace(conn, context.decision_trace)
            insert_backtest_regime_trace(conn, context.regime_trace)
            written.append(strategy.name)

        conn.commit()
    finally:
        conn.close()

    logger.debug("Backtest complete.")
    logger.debug("Covariance cache size: %s", len(returns_view.covariance_cache))
    logger.debug("Covariance cache hits: %s", returns_view.covariance_cache_hits)
    logger.debug("Covariance cache misses: %s", returns_view.covariance_cache_misses)
    return written


def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_backtests()


if __name__ == "__main__":
    main()
