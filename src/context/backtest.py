import pandas as pd
from src.engine.normalize import PriceNormalizer
from src.accounting.valuation import value_portfolio

class BacktestContext:
    def __init__(self, etf_history, macro_history, portfolio):
        self.etf_history = etf_history
        self.macro_history = macro_history
        self.portfolio = portfolio
        self.current_date = None
        self.decision_trace = []
        self.regime_trace = []
        self.results = []
        self.daily_metrics = [] 
        self.trade_log = []  

    def set_date(self, date):
        self.current_date = pd.Timestamp(date)

    def fetch_etf_prices(self):
        return self.etf_history[self.etf_history["date"] <= self.current_date]

    def fetch_macro_data(self):
        return self.macro_history[self.macro_history["date"] <= self.current_date]
    
    def get_prices_today(self) -> dict[str, float] | None:
        etf_df = self.fetch_etf_prices()
        return PriceNormalizer.normalize_prices(etf_df)
    
    @staticmethod
    def weights_from_holdings(holdings: dict[str, float], prices: dict[str, float], nav: float) -> dict[str, float]:
        nav = float(nav)
        if nav == 0.0:
            return {}

        out: dict[str, float] = {}
        for asset, units in holdings.items():
            if units == 0:
                continue
            px = float(prices[asset])
            out[asset] = (float(units) * px) / nav
        return out

    def persist(self, etf_df, macro_df, price_signals, macro_signals, decision):
        prices_today = PriceNormalizer.normalize_prices(self.fetch_etf_prices())
        snap = value_portfolio(
            date=str(self.current_date),
            cash=self.portfolio.cash,
            holdings=self.portfolio.holdings,
            prices=prices_today,
        )

        row = {
            "date": self.current_date,
            "nav": snap.nav,
        }

        # record target weights if present (decision intent)
        if "weights" in decision:
            for tkr, w in decision["weights"].items():
                row[f"tw_{tkr}"] = float(w)
        elif "chosen" in decision:
            row[f"tw_{decision['chosen']}"] = 1.0

        # record realized weights (actual portfolio state)
        rw = BacktestContext.weights_from_holdings(self.portfolio.holdings, prices_today, snap.nav)
        for tkr, w in rw.items():
            row[f"rw_{tkr}"] = float(w)

        self.results.append(row)


    def notify(self, *args):
        pass  # disabled

    def visualize(self, *args):
        pass  # disabled
