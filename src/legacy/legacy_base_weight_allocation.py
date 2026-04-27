from src.decision.models import Decision


TARGET_TICKERS = ["TLT", "AGG", "SHY"]


def _validate_decision(decision: Decision) -> None:
    if decision.regime is None:
        raise ValueError("Decision.regime must be populated before base allocation.")

    if decision.macro_state is None:
        raise ValueError("Decision.macro_state must be populated before base allocation.")

    if decision.price_state is None:
        raise ValueError("Decision.price_state must be populated before base allocation.")


def allocate_legacy_base_weights(decision: Decision) -> Decision:
    _validate_decision(decision)

    regime = decision.regime
    macro = decision.macro_state or {}
    price = decision.price_state or {}

    missing_prices = bool(price.get("missing_prices", False))
    ret_positive = price.get("ret_positive") or {}
    momentum = price.get("momentum") or {}

    tlt_pos = bool(ret_positive.get("TLT", momentum.get("TLT", False)))
    agg_pos = bool(ret_positive.get("AGG", momentum.get("AGG", False)))

    disinflation = bool(macro.get("disinflation", False))
    inflation_rising = bool(macro.get("inflation_rising", False))
    macro_supports_duration = bool(macro.get("macro_supports_duration", False))

    base_weights: dict[str, float]
    rule_id: str
    reason: str

    if regime == "data_fallback" or missing_prices:
        base_weights = {"TLT": 0.00, "AGG": 0.00, "SHY": 1.00}
        rule_id = "LEG_DATA_FALLBACK_SHY_001"
        reason = "Missing price signals -> fallback to SHY"

    elif inflation_rising:
        base_weights = {"TLT": 0.00, "AGG": 0.15, "SHY": 0.85}
        rule_id = "LEG_INF_WGT_001"
        reason = "Inflation rising -> heavily defensive (SHY), small AGG buffer"

    elif disinflation:
        if macro_supports_duration and tlt_pos:
            base_weights = {"TLT": 0.80, "AGG": 0.20, "SHY": 0.00}
            rule_id = "LEG_DIS_WGT_TLT_001"
            reason = "Strong disinflation + macro confirmation + TLT momentum -> overweight TLT"

        elif agg_pos:
            base_weights = {"TLT": 0.25, "AGG": 0.60, "SHY": 0.15}
            rule_id = "LEG_DIS_WGT_AGG_001"
            reason = "Disinflation but weak confirmation -> tilt AGG, keep some TLT + SHY"

        else:
            base_weights = {"TLT": 0.15, "AGG": 0.65, "SHY": 0.20}
            rule_id = "LEG_DIS_WGT_AGG_002"
            reason = "Disinflation but no positive momentum -> defensive AGG tilt"

    else:
        if agg_pos:
            base_weights = {"TLT": 0.10, "AGG": 0.75, "SHY": 0.15}
            rule_id = "LEG_NEU_WGT_AGG_001"
            reason = "Neutral inflation + AGG momentum -> overweight AGG"
        else:
            base_weights = {"TLT": 0.00, "AGG": 0.25, "SHY": 0.75}
            rule_id = "LEG_NEU_WGT_SHY_001"
            reason = "Neutral inflation + no positive momentum -> defensive mix (mostly SHY)"

    decision.legacy_base_weights = base_weights
    decision.notes.append(f"Legacy base allocator applied rule {rule_id}. Reason: {reason}")

    return decision