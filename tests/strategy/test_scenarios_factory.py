"""Scenario factory builders (src/scenarios/factory.py)."""

import pytest

from src.scenarios.factory import (
    build_scenario,
    build_vol_power_scenarios,
    build_covariance_scaling_scenarios,
    build_ewma_covariance_scaling_scenarios,
)
from src.scenarios.models import BacktestScenario

pytestmark = pytest.mark.unit


def test_build_scenario_propagates_config():
    s = build_scenario(
        scenario_id="x",
        vol_method="ewma",
        ewma_lambda=0.97,
        use_covariance_scaling=True,
        target_portfolio_vol=0.07,
    )
    assert isinstance(s, BacktestScenario)
    assert s.scenario_id == "x"
    assert s.volatility_config.method == "ewma"
    assert s.volatility_config.ewma_lambda == 0.97
    assert s.covariance_config.ewma_lambda == 0.97  # propagated to both configs
    assert s.position_sizing_config.use_covariance_scaling is True
    assert s.position_sizing_config.target_portfolio_vol == 0.07


def test_covariance_scaling_scenarios_cover_target_vols():
    scenarios = build_covariance_scaling_scenarios()
    assert len(scenarios) == 3
    target_vols = {s.position_sizing_config.target_portfolio_vol for s in scenarios}
    assert target_vols == {0.03, 0.05, 0.07}


def test_ewma_scenarios_cover_lambda_target_grid():
    scenarios = build_ewma_covariance_scaling_scenarios()
    assert len(scenarios) == 8  # 2 lambdas x 4 target vols
    assert all(s.covariance_config.method == "ewma_cov" for s in scenarios)


def test_vol_power_scenarios_nonempty():
    scenarios = build_vol_power_scenarios()
    assert len(scenarios) >= 1
    assert all(isinstance(s, BacktestScenario) for s in scenarios)
