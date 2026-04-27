from src.decision.models import Decision

TARGET_TICKERS = ["TLT", "AGG", "SHY"]


def _validate_decision(decision: Decision) -> None:
    if decision.regime is None:
        raise ValueError("Decision.regime must be populated before base allocation.")

    if decision.direction is None:
        raise ValueError("Decision.direction must be populated before base allocation.")

    if decision.price_state is None:
        raise ValueError("Decision.price_state must be populated before base allocation.")


def allocate_base_weights(decision: Decision) -> Decision:
    _validate_decision(decision)

    price = decision.price_state or {}
    direction = decision.direction or {}

    missing_prices = bool(price.get("missing_prices", False))

    if decision.regime == "data_fallback" or missing_prices:
        base_weights = {"TLT": 0.00, "AGG": 0.00, "SHY": 1.00}
        rule_id = "BASE_DATA_FALLBACK_SHY_001"
        reason = "Missing price signals -> fallback to SHY"

    else:
        tlt_on = bool(direction.get("TLT", 0))
        agg_on = bool(direction.get("AGG", 0))
        shy_on = bool(direction.get("SHY", 0))

        active = {
            "TLT": tlt_on,
            "AGG": agg_on,
            "SHY": shy_on,
        }
        # Set neutral values to define directions - let conviction and covariance deal with the rest

        if active == {"TLT": True, "AGG": True, "SHY": False}:
            base_weights = {"TLT": 0.45, "AGG": 0.45, "SHY": 0.10}
            rule_id = "BASE_TLT_AGG_001"
            reason = "TLT and AGG favoured -> duration-focused allocation"

        elif active == {"TLT": False, "AGG": True, "SHY": True}:
            base_weights = {"TLT": 0.00, "AGG": 0.50, "SHY": 0.50}
            rule_id = "BASE_AGG_SHY_001"
            reason = "AGG and SHY favoured -> balanced defensive allocation"

        elif active == {"TLT": True, "AGG": True, "SHY": True}:
            base_weights = {"TLT": 0.33, "AGG": 0.34, "SHY": 0.33}
            rule_id = "BASE_ALL_ON_001"
            reason = "All assets favoured -> diversified bond allocation"

        elif active == {"TLT": True, "AGG": False, "SHY": False}:
            base_weights = {"TLT": 0.80, "AGG": 0.20, "SHY": 0.00}
            rule_id = "BASE_TLT_ONLY_001"
            reason = "Only TLT favoured -> strong duration allocation with AGG buffer"

        elif active == {"TLT": False, "AGG": True, "SHY": False}:
            base_weights = {"TLT": 0.00, "AGG": 0.85, "SHY": 0.15}
            rule_id = "BASE_AGG_ONLY_001"
            reason = "Only AGG favoured -> aggregate bond allocation with SHY buffer"

        elif active == {"TLT": False, "AGG": False, "SHY": True}:
            base_weights = {"TLT": 0.00, "AGG": 0.00, "SHY": 1.00}
            rule_id = "BASE_SHY_ONLY_001"
            reason = "Only SHY favoured -> short-duration defensive allocation"

        else:
            base_weights = {"TLT": 0.00, "AGG": 0.25, "SHY": 0.75}
            rule_id = "BASE_DEFENSIVE_DEFAULT_001"
            reason = "No clear favourable asset set -> defensive default"

    decision.base_weights = base_weights
    decision.rule_id = rule_id
    decision.reason = reason
    decision.notes.append(f"Base allocator applied rule {rule_id}.")

    return decision