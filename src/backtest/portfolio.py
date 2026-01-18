from src.execution.models import ExecutionCosts
from src.execution.rebalance import generate_single_asset_rebalance_trades
from config import FEE_BPS, SLIPPAGE_BPS, MIN_TRADE_NOTIONAL
class Portfolio:
    def __init__(self, initial_capital):
        self.cash = initial_capital
        self.positions = {}     # asset -> shares
        self.nav = initial_capital
        self.current_asset = None
        self.units = 0.0

    def mark_to_market(self, prices):
        if self.current_asset is None:
            self.nav = self.cash
        else:
            price = prices[self.current_asset]
            self.nav = self.cash + self.units * price
    def apply_trades(self, trades):
        for t in trades:
            if t.side == "SELL":
                #liquidate shares
                self.cash += (t.notional_exec - t.fee_cost)
                self.units -= t.qty
                if self.units <= 1e-12:
                    self.units = 0.0
                    self.current_asset = None

            elif t.side == "BUY":
                self.cash -= (t.notional_exec + t.fee_cost)
                self.units += t.qty
                self.current_asset = t.ticker

        # clean floating point dust
        if abs(self.cash) < 1e-6:
            self.cash = 0.0


    def rebalance(self, decision, prices,date ):
        target = decision["chosen"]

        if self.current_asset == target:
            return []

        costs = ExecutionCosts(
            fee_bps=FEE_BPS,
            slippage_bps=SLIPPAGE_BPS,
            min_trade_notional=MIN_TRADE_NOTIONAL
        )

        trades = generate_single_asset_rebalance_trades(
            date=str(date),
            current_asset=self.current_asset,
            current_units=self.units,
            cash_available=self.cash,
            target_asset=target,
            prices=prices,
            costs=costs,
            reason="decision switch"
        )

        self.apply_trades(trades)
        return trades