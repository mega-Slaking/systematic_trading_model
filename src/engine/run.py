from src.decision.models import Decision
from src.signals_price.price_signal_engine import compute_price_signals
from src.signals_macro.macro_signal_engine import compute_macro_signals
from src.engine.decision_orchestration import orchestrate_decision_pipeline
from src.decision.decision_trace import record_decision
from src.decision.regime_trace import record_regime
from src.volatility import VolatilityConfig, VolatilityRequest, estimate_volatility
from src.covariance.models import CovarianceConfig
from src.covariance.estimator import estimate_covariance_from_returns_view
from src.covariance.returns_view import CovarianceReturnsView
from src.universe import UNIVERSE
from src.context.protocol import EngineContext
from src.strategy.config import StrategyConfig
from src.strategy.presets import STRATEGIES
import pandas as pd


def resolve_strategy(scenario=None, strategy=None) -> StrategyConfig:
    """Resolve the three possible config inputs into one StrategyConfig.

    Precedence: explicit ``strategy`` wins; otherwise a back-compat
    ``BacktestScenario`` is lifted into a StrategyConfig (conviction/constraints
    stay at their defaults, which is byte-identical to the old implicit None);
    otherwise the live-equivalent ``STRATEGIES["default"]`` is used.
    """
    if strategy is not None:
        return strategy
    if scenario is not None:
        return StrategyConfig(
            name=scenario.scenario_id,
            description=scenario.description,
            volatility=scenario.volatility_config,
            covariance=scenario.covariance_config,
            sizing=scenario.position_sizing_config,
        )
    return STRATEGIES["default"]


def run_engine(context: EngineContext, scenario=None, strategy=None):
    assert isinstance(context.current_date, pd.Timestamp), context.current_date
    etf_df = context.fetch_etf_prices()
    macro_df = context.fetch_macro_data()

    if etf_df.empty or macro_df.empty:
        return
    price_signals = compute_price_signals(etf_df)
    macro_signals = compute_macro_signals(macro_df)

    if price_signals.empty or macro_signals.empty:
        return

    # --- OLD config fork (commented out per project convention; replaced by
    # --- resolve_strategy + StrategyConfig). Kept as a rollback safety net.
    # if scenario is not None:
    #     vol_config = scenario.volatility_config
    #     cov_config = scenario.covariance_config
    #     sizing_config = scenario.position_sizing_config
    # else:
    #     vol_config = VolatilityConfig(
    #         method="rolling_std",
    #         lookback_days=20,
    #         annualization_factor=252,
    #         min_history=20,
    #     )
    #     cov_config = CovarianceConfig(
    #         method="sample_cov",
    #         lookback_days=20,
    #         annualization_factor=252,
    #         min_history=20,
    #     )
    #     sizing_config = None

    strategy = resolve_strategy(scenario=scenario, strategy=strategy)
    vol_config = strategy.volatility
    cov_config = strategy.covariance
    sizing_config = strategy.sizing

    vol_request = VolatilityRequest(
        etf_history=etf_df,
        as_of_date=context.current_date,
        tickers=list(UNIVERSE),
    )

    vol_estimate = estimate_volatility(vol_request, vol_config) #Asset-wise, returns vector with length 3

    # Passive volatility feature surface lookup (optional: only contexts that carry
    # a surface implement these, so accessed dynamically to keep the EngineContext
    # contract minimal). Features are lagged for lookahead safety and are NOT fed
    # into the decision pipeline yet.
    get_volatility_snapshot = getattr(context, "get_volatility_snapshot", None)
    snapshot_to_dict = getattr(context, "volatility_snapshot_to_dict", None)
    if get_volatility_snapshot is not None and snapshot_to_dict is not None:
        setattr(context, "volatility_features", snapshot_to_dict(get_volatility_snapshot()))

    # The backtest pre-builds and caches a returns view; the live context does not,
    # so fall back to building one from the fetched history.
    returns_view = getattr(context, "returns_view", None)
    if returns_view is None:
        returns_view = CovarianceReturnsView.from_etf_history(
            etf_history=etf_df,
            tickers=list(UNIVERSE),
        )

    cov_estimate = estimate_covariance_from_returns_view(
        returns_view=returns_view,
        as_of_date=context.current_date,
        tickers=list(UNIVERSE),
        config=cov_config,
    )

    decision = orchestrate_decision_pipeline(
        decision=Decision(date=context.current_date.isoformat()),
        price_signals=price_signals,
        macro_signals=macro_signals,
        conviction_config=strategy.conviction,   # NEW (was implicitly None == ConvictionConfig())
        vol_estimate=vol_estimate,
        cov_estimate=cov_estimate,
        sizing_config = sizing_config,
        constraints=strategy.constraints,         # NEW (was implicitly None == WeightConstraints())
    )
    record_decision(context, decision, price_signals, macro_signals) #refactored
    record_regime(context, macro_signals)

    context.persist(etf_df, macro_df, price_signals, macro_signals, decision) #
    context.notify(decision, price_signals, macro_signals) #
    context.visualize(etf_df, macro_df, price_signals, macro_signals, decision) #
    return decision