def record_regime(context, macro_signals):
    if macro_signals.empty:
        return

    latest = macro_signals.iloc[-1]

    context.regime_trace.append({
        "date": context.current_date,
        "inflation_regime": latest["inflation_regime"],
        "growth_regime": latest["growth_regime"],
        "labour_regime": latest["labour_regime"],
        "curve_state": latest["curve_state"],
        "macro_supports_duration": (
            latest["curve_inverted"] or
            latest["growth_slowing"] or
            latest["labor_weakening"]
        )
    })
