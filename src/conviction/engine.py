from __future__ import annotations

from src.decision.models import Decision
from src.conviction.models import ConvictionConfig, ConvictionEstimate


TARGET_TICKERS = ["TLT", "AGG", "SHY"]


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _safe_bool(value) -> bool:
    return bool(value) if value is not None else False


def _safe_float(value, default: float = 0.0) -> float:
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _average_bool_score(positives: list[bool], negatives: list[bool]) -> float:
    """
    Returns a score roughly between -1 and +1.

    More positive evidence pushes score up.
    More negative evidence pushes score down.
    """
    positive_score = sum(1 for x in positives if x) / len(positives) if positives else 0.0
    negative_score = sum(1 for x in negatives if x) / len(negatives) if negatives else 0.0

    return _clamp(positive_score - negative_score, -1.0, 1.0)


def _stagflation_pressure(macro: dict) -> bool:
    rates_hostile = (
        _safe_bool(macro.get("inflation_rising"))
        and _safe_bool(macro.get("real_rate_tight"))
    )

    economy_weakening = (
        _safe_bool(macro.get("growth_slowing"))
        or _safe_bool(macro.get("labor_weakening"))
        or _safe_bool(macro.get("jobless_rising"))
        or _safe_bool(macro.get("credit_spread_widening"))
    )

    return rates_hostile and economy_weakening


def _macro_score_tlt(macro: dict) -> float:
    """
    TLT likes disinflation and weakening growth/labour conditions,
    but should be penalised heavily when inflation/rates are hostile
    while the economy is weakening.
    """
    positives = [
        _safe_bool(macro.get("disinflation")),
        _safe_bool(macro.get("growth_slowing")),
        _safe_bool(macro.get("labor_weakening")),
        _safe_bool(macro.get("jobless_rising")),
        _safe_bool(macro.get("credit_spread_widening")),
        _safe_bool(macro.get("curve_inverted")),
    ]

    negatives = [
        _safe_bool(macro.get("inflation_rising")),
        _safe_bool(macro.get("real_rate_tight")),
    ]

    score = _average_bool_score(positives, negatives)

    if _stagflation_pressure(macro):
        score -= 0.50

    return _clamp(score, -1.0, 1.0)


def _macro_score_agg(macro: dict) -> float:
    """
    AGG is the balanced bond sleeve. It should be less penalised than TLT
    in stagflation, but still not rewarded strongly when inflation/rates
    are hostile.
    """
    positives = [
        _safe_bool(macro.get("disinflation")),
        _safe_bool(macro.get("growth_slowing")),
        _safe_bool(macro.get("curve_inverted")),
    ]

    negatives = [
        _safe_bool(macro.get("inflation_rising")),
        _safe_bool(macro.get("real_rate_tight")),
    ]

    score = _average_bool_score(positives, negatives)

    if _stagflation_pressure(macro):
        score -= 0.25

    return _clamp(score, -1.0, 1.0)


def _macro_score_shy(macro: dict) -> float:
    """
    SHY is the defensive / low-duration sleeve. It should benefit when
    inflation/rates are hostile and macro conditions are deteriorating.
    """
    positives = [
        _safe_bool(macro.get("inflation_rising")),
        _safe_bool(macro.get("real_rate_tight")),
        _safe_bool(macro.get("confidence_low")),
        _safe_bool(macro.get("credit_spread_widening")),
    ]

    negatives = [
        _safe_bool(macro.get("disinflation")),
        _safe_bool(macro.get("macro_supports_duration")),
    ]

    score = _average_bool_score(positives, negatives)

    if _stagflation_pressure(macro):
        score += 0.35

    return _clamp(score, -1.0, 1.0)


def _macro_score(ticker: str, macro: dict) -> float:
    if ticker == "TLT":
        return _macro_score_tlt(macro)

    if ticker == "AGG":
        return _macro_score_agg(macro)

    if ticker == "SHY":
        return _macro_score_shy(macro)

    return 0.0


def _price_score(ticker: str, price_state: dict, config: ConvictionConfig) -> float:
    """
    Preferred future input:
        price_state["ma_slope_z"]["TLT"]

    Fallback input:
        price_state["momentum"]["TLT"]
        price_state["returns"]["TLT"]

    The MA slope should eventually be volatility-normalised, e.g.
        ma_slope / rolling_vol
    """
    ma_slope_z = (price_state.get("ma_slope_z") or {}).get(ticker)

    if ma_slope_z is not None:
        return _clamp(_safe_float(ma_slope_z) / 2.0, -1.0, 1.0)

    if not config.use_price_fallback:
        return 0.0

    momentum = price_state.get("momentum") or {}
    returns = price_state.get("returns") or {}

    if ticker in momentum:
        return 1.0 if bool(momentum.get(ticker)) else -0.50

    ret = returns.get(ticker)

    if ret is None:
        return 0.0

    ret = _safe_float(ret)

    if ret > 0:
        return 1.0

    if ret < 0:
        return -0.50

    return 0.0


def _direction_score(ticker: str, direction: dict) -> float:
    """
    Direction is a light prior from favourable_asset_selection.

    It should not dominate conviction. It just says whether the asset is
    favoured by the regime layer.
    """
    return 1.0 if bool(direction.get(ticker, 0)) else -0.50


def _score_to_multiplier(score: float, config: ConvictionConfig) -> float:
    multiplier = 1.0 + (config.multiplier_sensitivity * score)
    return _clamp(multiplier, config.min_multiplier, config.max_multiplier)


def _normalise_weights(weights: dict[str, float]) -> dict[str, float]:
    gross = sum(max(0.0, float(v)) for v in weights.values())

    if gross <= 0:
        return {"TLT": 0.0, "AGG": 0.0, "SHY": 1.0}

    return {
        ticker: max(0.0, float(weights.get(ticker, 0.0))) / gross
        for ticker in TARGET_TICKERS
    }


def apply_conviction_scaling(
    decision: Decision,
    config: ConvictionConfig | None = None,
) -> Decision:
    config = config or ConvictionConfig()

    if decision.base_weights is None:
        raise ValueError("Decision.base_weights must be populated before conviction scaling.")

    if decision.macro_state is None:
        raise ValueError("Decision.macro_state must be populated before conviction scaling.")

    if decision.price_state is None:
        raise ValueError("Decision.price_state must be populated before conviction scaling.")

    if decision.direction is None:
        raise ValueError("Decision.direction must be populated before conviction scaling.")

    macro = decision.macro_state or {}
    price_state = decision.price_state or {}
    direction = decision.direction or {}

    conviction: dict[str, float] = {}
    raw_scores: dict[str, float] = {}
    component_scores: dict[str, dict[str, float]] = {}

    for ticker in TARGET_TICKERS:
        macro_component = _macro_score(ticker, macro)
        price_component = _price_score(ticker, price_state, config)
        direction_component = _direction_score(ticker, direction)

        raw_score = (
            config.macro_weight * macro_component
            + config.price_weight * price_component
            + config.direction_weight * direction_component
        )

        raw_score = _clamp(raw_score, -1.0, 1.0)

        raw_scores[ticker] = raw_score
        conviction[ticker] = _score_to_multiplier(raw_score, config)

        component_scores[ticker] = {
            "macro": macro_component,
            "price": price_component,
            "direction": direction_component,
            "raw": raw_score,
        }

    conviction_adjusted = {
        ticker: float(decision.base_weights.get(ticker, 0.0)) * conviction[ticker]
        for ticker in TARGET_TICKERS
    }

    conviction_weights = _normalise_weights(conviction_adjusted)

    decision.conviction = conviction
    decision.conviction_scores = raw_scores
    decision.conviction_components = component_scores
    decision.conviction_weights = conviction_weights

    decision.notes.append(
        "Conviction scaling applied using macro evidence, price confirmation, and favourable-asset direction."
    )

    return decision