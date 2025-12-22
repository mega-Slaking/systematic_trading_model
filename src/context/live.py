from src.api_fetch.fetch_etf_prices import fetch_etf_prices
from src.api_fetch.fetch_macro_data import fetch_macro_data
from src.storage.persister import save_run
from src.notify.notifier import send_notification
from src.visuals.visualizer import generate_daily_report
from src.engine.normalize import PriceNormalizer

import pandas as pd

class LiveContext:

    def __init__(self):
        self.current_date = pd.Timestamp.utcnow().normalize()

    def fetch_etf_prices(self):
        return fetch_etf_prices()

    def fetch_macro_data(self):
        return fetch_macro_data()
    
    def get_selected_price_today(self, selected: str) -> float:
        df = self.fetch_etf_prices()
        return PriceNormalizer.normalize_selected_price(df, selected)

    def persist(self, *args):
        save_run(*args)

    def notify(self, decision, price_signals, macro_signals):
        send_notification(decision, price_signals, macro_signals)

    def visualize(self, *args):
        generate_daily_report(*args)
