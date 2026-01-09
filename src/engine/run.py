from src.signals_price.price_signal_engine import compute_price_signals
from src.signals_macro.macro_signal_engine import compute_macro_signals
from src.decision.decision_engine import decide_allocation
from src.decision.decision_trace import record_decision
from src.decision.regime_trace import record_regime
import pandas as pd

def run_engine(context):
    assert isinstance(context.current_date, pd.Timestamp), context.current_date
    etf_df = context.fetch_etf_prices()
    macro_df = context.fetch_macro_data()
    assert not macro_df.empty, f"No macro data up to {context.current_date}"

    if etf_df.empty or macro_df.empty:
        return
    price_signals = compute_price_signals(etf_df)
    macro_signals = compute_macro_signals(macro_df)

    if price_signals.empty or macro_signals.empty:
        return
    
    decision = decide_allocation(price_signals, macro_signals)
    record_decision(context, decision, price_signals, macro_signals)
    record_regime(context, macro_signals)

    context.persist(etf_df, macro_df, price_signals, macro_signals, decision)
    context.notify(decision, price_signals, macro_signals)
    context.visualize(etf_df, macro_df, price_signals, macro_signals, decision)
    return decision