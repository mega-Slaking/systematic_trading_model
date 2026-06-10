"""StrategyConfig + with_() (src/strategy/config.py).

Asserts the composed config defaults match every sub-config's default (so the
live path reproduces today exactly) and that with_() routes each flat knob to the
correct nested sub-config while leaving the others untouched.
"""

import dataclasses

import pytest

from src.strategy.config import StrategyConfig, _FIELD_OWNERS
from src.volatility.models import VolatilityConfig
from src.covariance.models import CovarianceConfig
from src.decision.position_sizer_engine import PositionSizingConfig
from src.conviction.models import ConvictionConfig
from src.decision.constraints import WeightConstraints

pytestmark = pytest.mark.unit


def test_default_strategy_composes_subconfig_defaults():
    s = StrategyConfig()
    assert s.name == "default"
    assert s.description is None
    assert s.volatility == VolatilityConfig()
    assert s.covariance == CovarianceConfig()
    assert s.sizing == PositionSizingConfig()
    assert s.conviction == ConvictionConfig()
    assert s.constraints == WeightConstraints()


def test_default_reproduces_todays_live_sizing():
    # Live today: sizing_config=None -> size_positions builds PositionSizingConfig().
    # These are the knobs that silently drove the live book (vol-power 0.20 + cov on).
    sizing = StrategyConfig().sizing
    assert sizing.vol_scaling_power == 0.20
    assert sizing.use_covariance_scaling is True
    assert sizing.target_portfolio_vol == 0.10
    assert sizing.starting_weight_source == "conviction"


def test_default_reproduces_todays_inline_live_vol_and_cov():
    # Live today hardcoded these inline in run_engine (now commented out).
    s = StrategyConfig()
    assert s.volatility == VolatilityConfig(
        method="rolling_std", lookback_days=20, annualization_factor=252, min_history=20
    )
    assert s.covariance == CovarianceConfig(
        method="sample_cov", lookback_days=20, annualization_factor=252, min_history=20
    )


def test_with_is_immutable_and_returns_new_object():
    s = StrategyConfig()
    t = s.with_(use_covariance_scaling=False)
    assert t is not s
    assert s == StrategyConfig()  # original untouched (frozen)
    assert t.sizing.use_covariance_scaling is False


def test_with_routes_to_sizing_only():
    s = StrategyConfig()
    t = s.with_(use_vol_scaling=False, vol_scaling_power=0.5, target_portfolio_vol=0.03)
    assert t.sizing.use_vol_scaling is False
    assert t.sizing.vol_scaling_power == 0.5
    assert t.sizing.target_portfolio_vol == 0.03
    # other sub-configs untouched
    assert t.volatility == s.volatility
    assert t.covariance == s.covariance
    assert t.conviction == s.conviction
    assert t.constraints == s.constraints


def test_with_routes_to_volatility_only():
    s = StrategyConfig()
    t = s.with_(vol_method="ewma", vol_lookback_days=60, vol_ewma_lambda=0.97)
    assert t.volatility.method == "ewma"
    assert t.volatility.lookback_days == 60
    assert t.volatility.ewma_lambda == 0.97
    assert t.covariance == s.covariance
    assert t.sizing == s.sizing


def test_with_routes_to_covariance_only():
    s = StrategyConfig()
    t = s.with_(cov_method="ewma_cov", cov_lookback_days=60, cov_ewma_lambda=0.97)
    assert t.covariance.method == "ewma_cov"
    assert t.covariance.lookback_days == 60
    assert t.covariance.ewma_lambda == 0.97
    assert t.volatility == s.volatility
    assert t.sizing == s.sizing


def test_with_routes_to_constraints_only():
    s = StrategyConfig()
    t = s.with_(shy_floor=0.10)
    assert t.constraints.shy_floor == 0.10
    assert t.sizing == s.sizing
    assert t.volatility == s.volatility


def test_with_can_rename():
    s = StrategyConfig()
    assert s.with_(name="renamed").name == "renamed"
    # name defaults to the existing name when omitted
    assert s.with_(use_vol_scaling=False).name == "default"


def test_with_unknown_knob_raises():
    with pytest.raises(KeyError):
        StrategyConfig().with_(not_a_real_knob=1)


def test_field_owners_target_real_subconfig_fields():
    # Guard against drift: every (sub, field) in _FIELD_OWNERS must exist.
    s = StrategyConfig()
    for knob, (sub, fld) in _FIELD_OWNERS.items():
        sub_obj = getattr(s, sub)
        field_names = {f.name for f in dataclasses.fields(sub_obj)}
        assert fld in field_names, f"{knob!r} -> {sub}.{fld} does not exist"
