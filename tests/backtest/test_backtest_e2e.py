"""Full backtest end-to-end on synthetic data: data -> signals -> decision ->
execution -> accounting. Asserts it runs, produces a valid NAV path, and is
deterministic across runs.
"""

import pytest

from src.backtest.engine import run_backtest
from src.backtest.portfolio import Portfolio
from src.covariance.returns_view import CovarianceReturnsView
from src.scenarios.factory import build_scenario

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

TICKERS = ["TLT", "AGG", "SHY"]


def _run(etf, macro, scenario, returns_view):
    return run_backtest(
        etf,
        macro,
        Portfolio(1_000_000.0),
        scenario=scenario,
        returns_view=returns_view,
    )


def test_run_backtest_executes_valid_deterministic_path(
    synthetic_etf_history, synthetic_macro_history
):
    returns_view = CovarianceReturnsView.from_etf_history(
        etf_history=synthetic_etf_history, tickers=TICKERS
    )
    scenario = build_scenario(scenario_id="test_e2e")

    ctx1 = _run(synthetic_etf_history, synthetic_macro_history, scenario, returns_view)
    ctx2 = _run(synthetic_etf_history, synthetic_macro_history, scenario, returns_view)

    metrics = ctx1.daily_metrics
    assert len(metrics) > 0

    # NAV positive throughout; first marked NAV near the starting capital.
    assert all(m["nav"] > 0 for m in metrics)
    assert metrics[0]["nav_pre"] == pytest.approx(1_000_000.0, rel=1e-9)

    # Long-only, never levered above full investment.
    for m in metrics:
        assert sum(m["weights"].values()) <= 1.0 + 1e-6
        assert all(w >= -1e-9 for w in m["weights"].values())

    # Deterministic: identical NAV path across runs.
    nav1 = [m["nav"] for m in ctx1.daily_metrics]
    nav2 = [m["nav"] for m in ctx2.daily_metrics]
    assert nav1 == pytest.approx(nav2)
