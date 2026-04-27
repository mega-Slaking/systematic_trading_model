from src.covariance.models import CovarianceEstimate
from src.decision.models import Decision
from src.decision.position_sizer_engine import size_positions, PositionSizingConfig
from src.decision.constraint_engine import apply_final_constraints
from src.decision.constraints import WeightConstraints
from src.decision.pipeline import build_pre_risk_decision
from src.conviction.models import ConvictionConfig


def orchestrate_decision_pipeline(
    decision: Decision,
    price_signals,
    macro_signals,
    conviction_config: ConvictionConfig | None = None,
    vol_estimate=None,
    cov_estimate: CovarianceEstimate | None = None,
    sizing_config: PositionSizingConfig | None = None,
    constraints: WeightConstraints | None = None,
) -> Decision:

    decision = build_pre_risk_decision(decision=decision, price_signals=price_signals, 
                                       macro_signals=macro_signals, conviction_config=conviction_config)

    decision = size_positions(decision, vol_estimate=vol_estimate, cov_estimate=cov_estimate, config=sizing_config)
    #Position Sizing

    decision = apply_final_constraints(decision, constraints=constraints)
    #Final Constraints
    
    return decision