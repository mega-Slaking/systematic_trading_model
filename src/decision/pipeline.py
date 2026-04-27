from src.decision.models import Decision
from src.decision.regime_engine import evaluate_regime
from src.decision.favourable_asset_selection import determine_favourable_assets
from src.decision.base_allocator_engine import allocate_base_weights
from src.conviction.engine import apply_conviction_scaling
from src.conviction.models import ConvictionConfig
from src.legacy.legacy_base_weight_allocation import allocate_legacy_base_weights


def build_pre_risk_decision(
    decision: Decision,
    price_signals,
    macro_signals,
    conviction_config: ConvictionConfig | None = None,
) -> Decision:
    decision = evaluate_regime(
        decision=decision,
        price_signals=price_signals,
        macro_signals=macro_signals,
    )

    decision = allocate_legacy_base_weights(decision)

    decision = determine_favourable_assets(decision)

    decision = allocate_base_weights(decision)

    decision = apply_conviction_scaling(
        decision=decision,
        config=conviction_config,
    )

    return decision