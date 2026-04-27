from src.scenarios.models import BacktestScenario
from src.volatility.models import VolatilityConfig
from src.decision.position_sizer_engine import PositionSizingConfig
from src.covariance.models import CovarianceConfig


def build_scenario(
    *,
    scenario_id: str,
    vol_method: str = "rolling_std",
    lookback_days: int = 20,
    annualization_factor: int = 252,
    min_history: int = 20,
    ewma_lambda: float = 0.94,
    cov_ewma_lookback_days: int = 756,
    vol_scaling_power: float = 0.0,
    use_vol_scaling: bool = True,
    cov_method: str = "sample_cov",
    cov_lookback_days: int = 20,
    cov_annualization_factor: int = 252,
    cov_min_history: int = 20,
    use_covariance_scaling: bool = False,
    target_portfolio_vol: float = 0.10,
    starting_weight_source: str = "conviction",
    base_allocation_profile: str = "current",
    description: str | None = None,
) -> BacktestScenario:
    return BacktestScenario(
        scenario_id=scenario_id,
        volatility_config=VolatilityConfig(
            method=vol_method,
            lookback_days=lookback_days,
            annualization_factor=annualization_factor,
            min_history=min_history,
            ewma_lambda=ewma_lambda,
        ),
        covariance_config=CovarianceConfig(
            method=cov_method,
            lookback_days=cov_lookback_days,
            annualization_factor=cov_annualization_factor,
            min_history=cov_min_history,
            ewma_lambda=ewma_lambda,
            ewma_lookback_days=cov_ewma_lookback_days,
        ),
        position_sizing_config=PositionSizingConfig(
            use_vol_scaling=use_vol_scaling,
            vol_scaling_power=vol_scaling_power,
            use_covariance_scaling=use_covariance_scaling,
            target_portfolio_vol=target_portfolio_vol,
            starting_weight_source=starting_weight_source,
        ),
        description=description,
        base_allocation_profile=base_allocation_profile,
    )


def build_vol_power_scenarios() -> list[BacktestScenario]:
    vol_powers = [0.01]

    scenarios: list[BacktestScenario] = []

    for power in vol_powers:
        power_label = f"p{int(round(power * 100)):03d}"

        scenario = build_scenario(
            scenario_id=f"baseV1_roll20_{power_label}",
            vol_method="rolling_std",
            lookback_days=20,
            vol_scaling_power=power,
            use_vol_scaling=True,
            base_allocation_profile="baseV1",
            description=f"Base V1, rolling 20-day vol, vol power {power}",
        )
        scenarios.append(scenario)

    return scenarios

def build_covariance_scaling_scenarios() -> list[BacktestScenario]:
    target_vols = [0.03, 0.05, 0.07]

    scenarios: list[BacktestScenario] = []

    for target_vol in target_vols:
        vol_label = f"tv{int(round(target_vol * 100)):02d}"

        scenario = build_scenario(
            scenario_id=f"baseV1_roll20_covlb20_{vol_label}",
            vol_method="rolling_std",
            lookback_days=20,
            annualization_factor=252,
            min_history=20,
            vol_scaling_power=0.00,
            use_vol_scaling=False,
            cov_method="sample_cov",
            cov_lookback_days=20,
            cov_annualization_factor=252,
            cov_min_history=20,
            use_covariance_scaling=True,
            target_portfolio_vol=target_vol,
            base_allocation_profile="baseV1",
            description=(
                f"Base V1, rolling 20-day vol, sample covariance 20-day, "
                f"target portfolio vol {target_vol:.2f}, conviction off"
            ),
        )
        scenarios.append(scenario)

    return scenarios


def build_ewma_covariance_scaling_scenarios() -> list[BacktestScenario]:
    ewma_lambdas = [0.94, 0.97]
    target_vols = [0.02, 0.03, 0.04, 0.05]

    scenarios: list[BacktestScenario] = []

    for ewma_lambda in ewma_lambdas:
        lambda_label = f"lam{int(round(ewma_lambda * 100)):02d}"

        for target_vol in target_vols:
            vol_label = f"tv{int(round(target_vol * 100)):02d}"

            scenario = build_scenario(
                scenario_id=f"baseV1_roll20_ewmacov_{lambda_label}_{vol_label}",
                vol_method="rolling_std",
                lookback_days=20,
                annualization_factor=252,
                min_history=20,
                vol_scaling_power=0.00,
                use_vol_scaling=False,
                cov_method="ewma_cov",
                cov_annualization_factor=252,
                cov_min_history=20,
                ewma_lambda=ewma_lambda,
                use_covariance_scaling=True,
                target_portfolio_vol=target_vol,
                base_allocation_profile="baseV1",
                description=(
                    f"Base V1, rolling 20-day asset vol, EWMA covariance "
                    f"(lambda {ewma_lambda:.2f}), target portfolio vol {target_vol:.2f}, "
                    f"conviction off"
                ),
            )
            scenarios.append(scenario)

    return scenarios


def build_legacy_ewma_covariance_scaling_scenarios() -> list[BacktestScenario]:
    ewma_lambdas = [0.94, 0.97]
    target_vols = [0.02, 0.03, 0.04, 0.05]

    scenarios: list[BacktestScenario] = []

    for ewma_lambda in ewma_lambdas:
        lambda_label = f"lam{int(round(ewma_lambda * 100)):02d}"

        for target_vol in target_vols:
            vol_label = f"tv{int(round(target_vol * 100)):02d}"

            scenario = build_scenario(
                scenario_id=f"legacyBase_roll20_ewmacov_{lambda_label}_{vol_label}",
                vol_method="rolling_std",
                lookback_days=20,
                annualization_factor=252,
                min_history=20,
                vol_scaling_power=0.00,
                use_vol_scaling=False,
                cov_method="ewma_cov",
                cov_annualization_factor=252,
                cov_min_history=20,
                ewma_lambda=ewma_lambda,
                use_covariance_scaling=True,
                target_portfolio_vol=target_vol,
                starting_weight_source="legacy",
                base_allocation_profile="legacy_signal_weighted",
                description=(
                    f"Legacy signal-weighted base allocation, rolling 20-day asset vol, "
                    f"EWMA covariance lambda {ewma_lambda:.2f}, "
                    f"target portfolio vol {target_vol:.2f}"
                ),
            )
            scenarios.append(scenario)

    return scenarios


def build_legacy_covariance_scaling_scenarios() -> list[BacktestScenario]:
    target_vols = [0.03, 0.05]

    scenarios: list[BacktestScenario] = []

    for target_vol in target_vols:
        vol_label = f"tv{int(round(target_vol * 100)):02d}"

        scenario = build_scenario(
            scenario_id=f"legacyBase_roll20_covlb20_{vol_label}",
            vol_method="rolling_std",
            lookback_days=20,
            annualization_factor=252,
            min_history=20,
            vol_scaling_power=0.00,
            use_vol_scaling=False,
            cov_method="sample_cov",
            cov_lookback_days=20,
            cov_annualization_factor=252,
            cov_min_history=20,
            use_covariance_scaling=True,
            target_portfolio_vol=target_vol,
            starting_weight_source="legacy",
            base_allocation_profile="legacy_signal_weighted",
            description=(
                f"Legacy signal-weighted base allocation, rolling 20-day asset vol, "
                f"sample covariance 20-day, target portfolio vol {target_vol:.2f}"
            ),
        )
        scenarios.append(scenario)

    return scenarios