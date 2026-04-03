UNIVERSE = ["TLT", "AGG", "SHY"]


def record_decision(context, decision, price_signals, macro_signals):
    weights = dict(decision.final_weights or {})

    # fallback if something went wrong upstream
    if not weights and decision.base_weights:
        weights = dict(decision.base_weights)

    macro = decision.macro_state or {}

    trace = {
        "date": context.current_date,
        "rule_id": decision.rule_id,

        "disinflation": macro.get("disinflation"),
        "curve_inverted": macro.get("curve_inverted"),
        "growth_slowing": macro.get("growth_slowing"),
        "labor_weakening": macro.get("labor_weakening"),

        "chosen_asset": max(weights, key=weights.get) if weights else None,
    }

    for tkr in UNIVERSE:
        trace[f"w_{tkr}"] = float(weights.get(tkr, 0.0))

    context.decision_trace.append(trace)