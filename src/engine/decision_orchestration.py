from src.covariance.models import CovarianceEstimate
from src.decision.models import Decision
from src.decision.regime_engine import evaluate_regime
from src.decision.base_allocator_engine import allocate_base_weights
from src.decision.position_sizer_engine import size_positions, PositionSizingConfig
from src.decision.constraint_engine import apply_final_constraints
from src.decision.constraints import WeightConstraints


def orchestrate_decision_pipeline(
    decision: Decision,
    price_signals,
    macro_signals,
    vol_estimate=None,
    cov_estimate: CovarianceEstimate | None = None,
    sizing_config: PositionSizingConfig | None = None,
    constraints: WeightConstraints | None = None,
) -> Decision:
    
    decision = evaluate_regime(decision, price_signals, macro_signals)
    #Regime

    decision = allocate_base_weights(decision)
    #Base Allocation

    decision = size_positions(decision, vol_estimate=vol_estimate, cov_estimate=cov_estimate, config=sizing_config)
    #Position Sizing

    decision = apply_final_constraints(decision, constraints=constraints)
    #Final Constraints
    
    return decision