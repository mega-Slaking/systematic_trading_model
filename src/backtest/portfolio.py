import pandas as pd
class Portfolio:
    def __init__(self, initial_capital):
        self.cash = initial_capital
        self.positions = {}     # asset -> shares
        self.nav = initial_capital
        self.current_asset = None

    def mark_to_market(self, prices):
        if self.current_asset is None:
            self.nav = self.cash
        else:
            price = prices[self.current_asset]
            self.nav = self.cash + self.units * price

    def rebalance(self, decision, prices):
        target = decision["chosen"]

        if self.current_asset == target:
            return

        # exit current
        if self.current_asset is not None:
            exit_price = prices[self.current_asset]
            self.cash += self.units * exit_price
            self.units = 0.0

        # enter new
        entry_price = prices[target]
        self.units = self.cash / entry_price
        self.cash = 0.0
        self.current_asset = target
