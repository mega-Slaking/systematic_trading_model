from dataclasses import dataclass, field
from typing import Optional
from src.volatility.models import VolatilityConfig
from src.covariance.models import CovarianceConfig
from src.decision.position_sizer_engine import PositionSizingConfig


@dataclass(frozen=True)
class BacktestScenario:
    scenario_id: str
    volatility_config: VolatilityConfig
    covariance_config: CovarianceConfig
    position_sizing_config: PositionSizingConfig
    description: Optional[str] = None
    base_allocation_profile: str = "baseV1"
    conviction_profile: str = "convOff"