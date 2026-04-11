from src.decision.models import Decision
from src.signals_price.price_signal_engine import compute_price_signals
from src.signals_macro.macro_signal_engine import compute_macro_signals
from src.engine.decision_orchestration import orchestrate_decision_pipeline
from src.decision.decision_trace import record_decision
from src.decision.regime_trace import record_regime
from src.volatility import VolatilityConfig, VolatilityRequest, estimate_volatility
import pandas as pd

def run_engine(context,scenario=None):
    assert isinstance(context.current_date, pd.Timestamp), context.current_date
    etf_df = context.fetch_etf_prices()
    macro_df = context.fetch_macro_data()

    if etf_df.empty or macro_df.empty:
        return
    price_signals = compute_price_signals(etf_df)
    macro_signals = compute_macro_signals(macro_df)

    if price_signals.empty or macro_signals.empty:
        return
    
    if scenario is not None:
        vol_config = scenario.volatility_config
        sizing_config = scenario.position_sizing_config
    else:
        vol_config = VolatilityConfig(
            method="rolling_std",
            lookback_days=20,
            annualization_factor=252,
            min_history=20,
        )
        sizing_config = None

    vol_request = VolatilityRequest(
        etf_history=etf_df,
        as_of_date=context.current_date,
        tickers=["TLT", "AGG", "SHY"],
    )

    vol_estimate = estimate_volatility(vol_request, vol_config) #Asset-wise, returns vector with length 3

    decision = orchestrate_decision_pipeline(
        decision=Decision(date=context.current_date.isoformat()),
        price_signals=price_signals,
        macro_signals=macro_signals,
        vol_estimate=vol_estimate,
        sizing_config = sizing_config,
    )
    record_decision(context, decision, price_signals, macro_signals) #refactored
    record_regime(context, macro_signals)

    context.persist(etf_df, macro_df, price_signals, macro_signals, decision) #
    context.notify(decision, price_signals, macro_signals) #
    context.visualize(etf_df, macro_df, price_signals, macro_signals, decision) #
    return decision