UNIVERSE = ["TLT", "AGG", "SHY"]

def record_decision(context, decision, price_signals, macro_signals):
    weights = dict(decision.get("weights") or {})
    chosen = decision.get("chosen")

    if chosen and not weights:
        weights = {chosen: 1.0}

    trace = {
        "date": context.current_date,
        "rule_id": decision.get("rule_id"),

        "disinflation": decision.get("macro", {}).get("disinflation"),
        "curve_inverted": decision.get("macro", {}).get("curve_inverted"),
        "growth_slowing": decision.get("macro", {}).get("growth_slowing"),
        "labor_weakening": decision.get("macro", {}).get("labor_weakening"),

        "chosen_asset": max(weights, key=weights.get) if weights else None,
    }

    # fixed columns, always present
    for tkr in UNIVERSE:
        trace[f"w_{tkr}"] = float(weights.get(tkr, 0.0))

    context.decision_trace.append(trace)