from src.decision.models import Decision
from src.decision.regime_engine import evaluate_regime
from src.legacy.legacy_base_weight_allocation import allocate_legacy_base_weights
from src.strategy.tlt_tracker import allocate_tlt_tracker_weights, TltTrackerConfig
from src.conviction.models import ConvictionConfig

# --- OLD modern allocator path (regime -> direction -> base table -> conviction
# --- tilt). Replaced by the TLT-tracking allocator below. The two table modules
# --- were moved to src/legacy/; the conviction module stays in place but is no
# --- longer called from the pre-risk path. Kept commented as a rollback safety
# --- net (project convention). The regime-table logic remains unit-tested
# --- directly: tests/strategy/test_favourable_assets.py, test_base_allocator.py.
# from src.legacy.favourable_asset_selection import determine_favourable_assets
# from src.legacy.base_allocator_engine import allocate_base_weights
# from src.conviction.engine import apply_conviction_scaling


def build_pre_risk_decision(
    decision: Decision,
    price_signals,
    macro_signals,
    conviction_config: ConvictionConfig | None = None,   # retained for the commented conviction path
    allocator_config: TltTrackerConfig | None = None,
) -> Decision:
    decision = evaluate_regime(
        decision=decision,
        price_signals=price_signals,
        macro_signals=macro_signals,
    )

    # Legacy signal-weighted table is still produced so strategies with
    # starting_weight_source="legacy" keep working (the position sizer reads
    # decision.legacy_base_weights for that source).
    decision = allocate_legacy_base_weights(decision)

    # --- OLD modern path (commented per convention; replaced by the TLT tracker):
    # decision = determine_favourable_assets(decision)
    # decision = allocate_base_weights(decision)
    # decision = apply_conviction_scaling(decision=decision, config=conviction_config)

    # NEW base strategy: follow TLT on confirmed uptrends (with a lag), buffer
    # into AGG/SHY on confirmed downtrends. Writes base_weights AND
    # conviction_weights so the sizer (starting_weight_source="conviction")
    # consumes the tracker's directional weights unchanged.
    decision = allocate_tlt_tracker_weights(decision, price_signals, config=allocator_config)

    return decision
