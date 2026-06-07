"""The interface `run_engine` requires of an execution context.

`BacktestContext` and `LiveContext` both satisfy this structurally (no inheritance
needed). Optional capabilities `run_engine` uses -- `returns_view` and the
volatility-surface hooks -- are accessed defensively there and are deliberately
NOT part of this minimal contract.

Marked `runtime_checkable` so the test suite can assert conformance via
`isinstance`, catching a context that drifts away from the contract at test time
(no external type checker required).
"""

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class EngineContext(Protocol):
    current_date: Any  # pd.Timestamp once a date has been set

    def fetch_etf_prices(self) -> pd.DataFrame: ...

    def fetch_macro_data(self) -> pd.DataFrame: ...

    def persist(
        self, etf_df: Any, macro_df: Any, price_signals: Any, macro_signals: Any, decision: Any, /
    ) -> None: ...

    def notify(self, decision: Any, price_signals: Any, macro_signals: Any, /) -> None: ...

    def visualize(
        self, etf_df: Any, macro_df: Any, price_signals: Any, macro_signals: Any, decision: Any, /
    ) -> None: ...


if TYPE_CHECKING:
    # Static (pyright) conformance check: both concrete contexts must satisfy
    # EngineContext. Drift here is a CI failure, not a runtime AttributeError.
    from src.context.backtest import BacktestContext
    from src.context.live import LiveContext

    def _assert_contexts_conform(backtest: BacktestContext, live: LiveContext) -> None:
        _b: EngineContext = backtest
        _l: EngineContext = live
