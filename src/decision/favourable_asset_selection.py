from src.decision.models import Decision


def determine_favourable_assets(decision: Decision) -> Decision:
    if decision.regime is None:
        raise ValueError("Decision.regime must be populated before favourable asset selection.")

    regime = decision.regime
    macro = decision.macro_state or {} #why is macro here?

    if regime == "data_fallback":
        direction = {"TLT": 0, "AGG": 0, "SHY": 1}
        reason = "Data fallback -> favour SHY"

    elif regime == "dovish_bearish":
        direction = {"TLT": 1, "AGG": 1, "SHY": 0}
        reason = "Dovish + bearish -> favour duration"

    elif regime == "dovish_neutral":
        direction = {"TLT": 1, "AGG": 1, "SHY": 0}
        reason = "Dovish + neutral -> favour duration and aggregate bonds"

    elif regime == "dovish_bullish":
        direction = {"TLT": 1, "AGG": 1, "SHY": 0}
        reason = "Dovish + bullish -> favourable bond backdrop, but less defensive need"

    elif regime == "hawkish_bearish":
        direction = {"TLT": 0, "AGG": 0, "SHY": 1}
        reason = "Hawkish + bearish -> stagflation-style risk, favour short duration"

    elif regime == "hawkish_neutral":
        direction = {"TLT": 0, "AGG": 1, "SHY": 1}
        reason = "Hawkish + neutral -> avoid long duration, favour AGG/SHY"

    elif regime == "hawkish_bullish":
        direction = {"TLT": 0, "AGG": 1, "SHY": 1}
        reason = "Hawkish + bullish -> growth can absorb rates, but long duration still unattractive"

    elif regime == "neutral_bearish":
        direction = {"TLT": 1, "AGG": 1, "SHY": 1}
        reason = "Neutral policy + bearish economy -> mixed defensive bond support"

    elif regime == "neutral_bullish":
        direction = {"TLT": 0, "AGG": 1, "SHY": 1}
        reason = "Neutral policy + bullish economy -> balanced AGG/SHY preference"

    else:
        direction = {"TLT": 0, "AGG": 1, "SHY": 1}
        reason = "Neutral/mixed regime -> favour balanced defensive assets"

    decision.direction = direction
    decision.notes.append(f"Favourable assets selected: {reason}")

    return decision