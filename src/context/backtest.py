import pandas as pd
from src.engine.normalize import PriceNormalizer

class BacktestContext:
    def __init__(self, etf_history, macro_history, portfolio):
        self.etf_history = etf_history
        self.macro_history = macro_history
        self.portfolio = portfolio
        self.current_date = None
        self.results = []

    def set_date(self, date):
        self.current_date = pd.Timestamp(date)

    def fetch_etf_prices(self):
        return self.etf_history[self.etf_history["date"] <= self.current_date]

    def fetch_macro_data(self):
        return self.macro_history[self.macro_history["date"] <= self.current_date]
    
    def get_prices_today(self) -> dict[str, float]:
        etf_df = self.fetch_etf_prices()
        return PriceNormalizer.normalize_prices(etf_df)

    def persist(self, etf_df, macro_df, price_signals, macro_signals, decision):
        self.results.append({
            "date": self.current_date,
            "nav": self.portfolio.nav,
            "asset": decision["chosen"]
        })


    def notify(self, *args):
        pass  # disabled

    def visualize(self, *args):
        pass  # disabled
