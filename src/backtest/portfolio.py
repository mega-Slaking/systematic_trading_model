from src.execution.models import ExecutionCosts
from src.execution.rebalance import generate_single_asset_rebalance_trades
#import new rebalance module
from src.execution.rebalance_v2 import generate_weight_rebalance_trades
from src.utils.weights import normalize_weights, clip_weights
from config import FEE_BPS, SLIPPAGE_BPS, MIN_TRADE_NOTIONAL, DRIFT_TOL
class Portfolio:
    def __init__(self, initial_capital):
        self.cash = float(initial_capital)
        self.holdings = {}  # ticker -> shares
        self.nav = float(initial_capital)

        # V1 legacy fields (keep for now)
        self.current_asset = None
        self.units = 0.0

    def mark_to_market(self, prices):
        mv = 0.0
        for tkr, sh in self.holdings.items():
            if tkr in prices:
                mv += float(sh) * float(prices[tkr])
        self.nav = self.cash + mv

        # Optional: keep legacy fields consistent for reporting if you want
        # If exactly one non-zero position, reflect it:
        non_zero = [(t, sh) for t, sh in self.holdings.items() if abs(float(sh)) > 1e-12]
        if len(non_zero) == 1:
            self.current_asset, self.units = non_zero[0][0], float(non_zero[0][1])
        else:
            self.current_asset, self.units = None, 0.0

    def apply_trades(self, trades):
        for t in trades:
            tkr = t.ticker
            sh = float(self.holdings.get(tkr, 0.0))

            if t.side == "SELL":
                self.cash += (t.notional_exec - t.fee_cost)
                sh -= float(t.qty)
            elif t.side == "BUY":
                self.cash -= (t.notional_exec + t.fee_cost)
                sh += float(t.qty)

            # clean dust
            if abs(sh) <= 1e-12:
                sh = 0.0
            self.holdings[tkr] = sh

        # clean floating point dust in cash
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
    
    #Version 2 rebalance
    def rebalance_v2(self, decision, prices, date):

        raw_weights = decision["weights"]

        weights = normalize_weights(
            clip_weights(raw_weights)
        )

        costs = ExecutionCosts(
            fee_bps=FEE_BPS,
            slippage_bps=SLIPPAGE_BPS,
            min_trade_notional=MIN_TRADE_NOTIONAL,
        )

        trades = generate_weight_rebalance_trades(
            date=str(date),
            positions=self.holdings,
            cash_available=self.cash,
            target_weights=weights,
            prices=prices,
            costs=costs,
            reason="decision weights",
            drift_tol=DRIFT_TOL,
        )

        if trades:
            self.apply_trades(trades)

        return trades