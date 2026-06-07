"""Both contexts must satisfy the EngineContext contract that run_engine relies on.

This guards the drift class that broke the live run: run_engine reaching for a
member a context doesn't provide. If a context loses a required member, these fail.
"""

import pytest

from src.context.protocol import EngineContext
from src.context.backtest import BacktestContext
from src.context.live import LiveContext

pytestmark = pytest.mark.unit


def test_backtest_context_satisfies_engine_context():
    ctx = BacktestContext(etf_history=None, macro_history=None, portfolio=None)
    assert isinstance(ctx, EngineContext)


def test_live_context_satisfies_engine_context():
    assert isinstance(LiveContext(), EngineContext)
