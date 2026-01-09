def record_decision(context, decision, price_signals, macro_signals):
    context.decision_trace.append({
        "date": context.current_date,
        "chosen_asset": decision["chosen"],
        "rule_id": decision["rule_id"],
        #"reason": decision.get("reason"),

        # macro state
        "disinflation": decision["macro"]["disinflation"],
        "curve_inverted": decision["macro"]["curve_inverted"],
        "growth_slowing": decision["macro"]["growth_slowing"],
        "labor_weakening": decision["macro"]["labor_weakening"],

        # price state
        "tlt_pos": decision["tlt_ret"] > 0,
        "agg_pos": decision["agg_ret"] > 0
    })
