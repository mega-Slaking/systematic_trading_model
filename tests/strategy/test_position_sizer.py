"""Position sizer: covariance scaling + SHY buffer + no-leverage cap + vol scaling
(src/decision/position_sizer_engine.py). This exercises the risk-sizing math that
was previously only hit via the no-op path.
"""

import pandas as pd
import pytest

from src.decision.models import Decision
from src.decision.position_sizer_engine import size_positions, PositionSizingConfig
from src.covariance.models import CovarianceEstimate
from src.volatility.models import VolatilityEstimate

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def _cov_estimate():
    # Uncorrelated; annualized vols TLT=0.20, AGG=0.10, SHY=0.01.
    df = pd.DataFrame(
        [[0.04, 0.0, 0.0], [0.0, 0.01, 0.0], [0.0, 0.0, 0.0001]],
        index=["TLT", "AGG", "SHY"],
        columns=["TLT", "AGG", "SHY"],
    )
    return CovarianceEstimate(
        method="sample_cov",
        as_of_date=pd.Timestamp("2020-06-01"),
        annualized=True,
        tickers=["TLT", "AGG", "SHY"],
        covariance_matrix=df,
        notes=[],
        invalid_tickers=[],
    )


def _decision():
    return Decision(date="d", conviction_weights={"TLT": 0.5, "AGG": 0.5, "SHY": 0.0})


# Current portfolio vol of the 50/50 TLT/AGG sleeve:
# sqrt(0.5^2*0.04 + 0.5^2*0.01) = sqrt(0.0125) = 0.1118034
CURRENT_VOL = 0.111803398


def test_derisks_into_shy_when_vol_above_target():
    cfg = PositionSizingConfig(
        use_vol_scaling=False,
        use_covariance_scaling=True,
        target_portfolio_vol=0.05,
        starting_weight_source="conviction",
    )
    out = size_positions(_decision(), vol_estimate=None, cov_estimate=_cov_estimate(), config=cfg)

    scale = 0.05 / CURRENT_VOL
    assert out.portfolio_vol_estimate == pytest.approx(CURRENT_VOL, abs=1e-6)
    assert out.portfolio_scale == pytest.approx(scale, abs=1e-6)
    assert out.sized_weights["TLT"] == pytest.approx(0.5 * scale, abs=1e-6)
    assert out.sized_weights["AGG"] == pytest.approx(0.5 * scale, abs=1e-6)
    # SHY absorbs the de-risked remainder; portfolio stays fully invested.
    assert out.sized_weights["SHY"] == pytest.approx(1.0 - scale, abs=1e-6)
    assert sum(out.sized_weights.values()) == pytest.approx(1.0)


def test_caps_at_no_leverage_when_vol_below_target():
    cfg = PositionSizingConfig(
        use_vol_scaling=False,
        use_covariance_scaling=True,
        target_portfolio_vol=0.20,  # above current 0.1118 -> wants to scale up
        starting_weight_source="conviction",
    )
    out = size_positions(_decision(), vol_estimate=None, cov_estimate=_cov_estimate(), config=cfg)

    assert out.portfolio_scale == pytest.approx(1.0)  # capped, no borrowing
    assert out.sized_weights["TLT"] == pytest.approx(0.5)
    assert out.sized_weights["AGG"] == pytest.approx(0.5)
    assert out.sized_weights["SHY"] == pytest.approx(0.0)


def test_covariance_scaling_disabled_is_passthrough():
    cfg = PositionSizingConfig(
        use_vol_scaling=False, use_covariance_scaling=False, starting_weight_source="conviction"
    )
    out = size_positions(_decision(), cov_estimate=_cov_estimate(), config=cfg)
    assert out.portfolio_scale == 1.0
    assert out.sized_weights == pytest.approx({"TLT": 0.5, "AGG": 0.5, "SHY": 0.0})


def test_vol_scaling_tilts_toward_lower_vol_asset():
    # max_asset_weight lifted so the per-asset cap doesn't clip the tilt away.
    cfg = PositionSizingConfig(
        use_vol_scaling=True,
        vol_scaling_power=1.0,
        use_covariance_scaling=False,
        max_asset_weight=10.0,
        starting_weight_source="conviction",
    )
    vol = VolatilityEstimate(
        method="rolling_std",
        as_of_date=pd.Timestamp("2020-06-01"),
        annualized=True,
        vols={"TLT": 0.20, "AGG": 0.05, "SHY": 0.01},
    )
    out = size_positions(_decision(), vol_estimate=vol, cov_estimate=None, config=cfg)
    # weight / vol^1 -> TLT: 0.5/0.20=2.5, AGG: 0.5/0.05=10 -> normalize -> 0.2 / 0.8
    assert out.sized_weights["TLT"] == pytest.approx(0.2)
    assert out.sized_weights["AGG"] == pytest.approx(0.8)
    assert sum(out.sized_weights.values()) == pytest.approx(1.0)
