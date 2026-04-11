from src.scenarios.models import BacktestScenario
from src.volatility.models import VolatilityConfig
from src.decision.position_sizer_engine import PositionSizingConfig


def build_scenario(
    *,
    scenario_id: str,
    vol_method: str = "rolling_std",
    lookback_days: int = 20,
    annualization_factor: int = 252,
    min_history: int = 20,
    vol_scaling_power: float = 0.0,
    use_vol_scaling: bool = True,
    use_conviction_scaling: bool = False,
    base_allocation_profile: str = "baseV1",
    conviction_profile: str = "convOff",
    description: str | None = None,
) -> BacktestScenario:
    return BacktestScenario(
        scenario_id=scenario_id,
        volatility_config=VolatilityConfig(
            method=vol_method,
            lookback_days=lookback_days,
            annualization_factor=annualization_factor,
            min_history=min_history,
        ),
        position_sizing_config=PositionSizingConfig(
            use_vol_scaling=use_vol_scaling,
            use_conviction_scaling=use_conviction_scaling,
            vol_scaling_power=vol_scaling_power,
        ),
        description=description,
        base_allocation_profile=base_allocation_profile,
        conviction_profile=conviction_profile,
    )


def build_vol_power_scenarios() -> list[BacktestScenario]:
    vol_powers = [0.00, 0.20, 0.30]

    scenarios: list[BacktestScenario] = []

    for power in vol_powers:
        power_label = f"p{int(round(power * 100)):03d}"

        scenario = build_scenario(
            scenario_id=f"baseV1_roll20_{power_label}_convOff",
            vol_method="rolling_std",
            lookback_days=20,
            vol_scaling_power=power,
            use_vol_scaling=True,
            use_conviction_scaling=False,
            base_allocation_profile="baseV1",
            conviction_profile="convOff",
            description=f"Base V1, rolling 20-day vol, vol power {power}, conviction off",
        )
        scenarios.append(scenario)

    return scenarios