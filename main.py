from src.api_fetch.fetch_etf_prices import fetch_etf_prices
from src.api_fetch.fetch_macro_data import fetch_macro_data
from src.signals_price.price_signal_engine import compute_price_signals
from src.signals_macro.macro_signal_engine import compute_macro_signals
from src.decision.decision_engine import decide_allocation
from src.storage.persister import save_run
from src.notify.notifier import send_notification
from src.visuals.visualizer import generate_daily_report

def main():
    # Fetch data
    etf_df = fetch_etf_prices()
    macro_df = fetch_macro_data()

    # Compute signals
    price_signals = compute_price_signals(etf_df)
    macro_signals = compute_macro_signals(macro_df)

    # Decide allocation
    decision = decide_allocation(price_signals, macro_signals)

    # Persist
    save_run(etf_df, macro_df, price_signals, macro_signals, decision)

    # Notify
    send_notification(decision, price_signals, macro_signals)

    # Visuals (optional)
    generate_daily_report(etf_df, macro_df, price_signals, macro_signals, decision)

if __name__ == "__main__":
    main()
