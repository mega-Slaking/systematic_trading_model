"""Scenario factory (src/scenarios/factory.py).

The five grid builders (build_vol_power_scenarios, build_covariance_scaling_scenarios,
etc.) were retired in V1.10.0 in favour of the src/strategy/presets.py STRATEGIES
registry (they are commented out as a rollback safety net). Their coverage now
lives in tests/strategy/test_presets.py. Only build_scenario remains live here -
it is the back-compat scenario path still used by the e2e test and lifted into a
StrategyConfig by resolve_strategy.
"""

import pytest

from src.scenarios.factory import build_scenario
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


def test_build_scenario_defaults():
    s = build_scenario(scenario_id="defaults")
    assert s.volatility_config.method == "rolling_std"
    assert s.volatility_config.lookback_days == 20
    assert s.covariance_config.method == "sample_cov"
    # build_scenario's own default differs from PositionSizingConfig()'s default.
    assert s.position_sizing_config.use_covariance_scaling is False
    assert s.position_sizing_config.vol_scaling_power == 0.0
    assert s.position_sizing_config.starting_weight_source == "conviction"
