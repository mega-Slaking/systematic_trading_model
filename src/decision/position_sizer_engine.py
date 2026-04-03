from dataclasses import dataclass
from typing import Dict

from src.decision.models import Decision


TARGET_TICKERS = ["TLT", "AGG", "SHY"]


@dataclass
class PositionSizingConfig:
    target_gross: float = 1.0
    min_vol: float = 1e-6
    max_asset_weight: float = 1.0
    use_vol_scaling: bool = True
    use_conviction_scaling: bool = True
    fallback_to_base_if_empty: bool = True


def _validate_base_weights(decision: Decision) -> Dict[str, float]:
    if decision.base_weights is None:
        raise ValueError("Decision.base_weights must be populated before position sizing.")

    weights = {ticker: float(decision.base_weights.get(ticker, 0.0)) for ticker in TARGET_TICKERS}

    if not weights:
        raise ValueError("Decision.base_weights is empty.")

    return weights


def _copy_weights(weights: Dict[str, float]) -> Dict[str, float]:
    return {ticker: float(value) for ticker, value in weights.items()}


def _gross_exposure(weights: Dict[str, float]) -> float:
    return sum(abs(float(w)) for w in weights.values())


def _net_exposure(weights: Dict[str, float]) -> float:
    return sum(float(w) for w in weights.values())


def _apply_volatility_scaling(
    weights: Dict[str, float],
    vols: Dict[str, float] | None,
    config: PositionSizingConfig,
) -> Dict[str, float]:
    if not config.use_vol_scaling:
        return _copy_weights(weights)

    if not vols:
        return _copy_weights(weights)

    scaled: Dict[str, float] = {}

    for ticker, weight in weights.items():
        vol = float(vols.get(ticker, 0.0))
        effective_vol = max(vol, config.min_vol)

        if weight == 0.0:
            scaled[ticker] = 0.0
            continue

        scaled[ticker] = float(weight) / effective_vol

    return scaled


def _apply_conviction_scaling(
    weights: Dict[str, float],
    conviction: Dict[str, float] | None,
    config: PositionSizingConfig,
) -> Dict[str, float]:
    if not config.use_conviction_scaling:
        return _copy_weights(weights)

    if not conviction:
        return _copy_weights(weights)

    scaled: Dict[str, float] = {}

    for ticker, weight in weights.items():
        conviction_mult = float(conviction.get(ticker, 1.0))
        scaled[ticker] = float(weight) * conviction_mult

    return scaled


def _apply_asset_caps(
    weights: Dict[str, float],
    config: PositionSizingConfig,
) -> Dict[str, float]:
    capped: Dict[str, float] = {}

    cap = float(config.max_asset_weight)

    for ticker, weight in weights.items():
        if weight > cap:
            capped[ticker] = cap
        elif weight < -cap:
            capped[ticker] = -cap
        else:
            capped[ticker] = float(weight)

    return capped


def _normalize_to_target_gross(
    weights: Dict[str, float],
    config: PositionSizingConfig,
) -> Dict[str, float]:
    gross = _gross_exposure(weights)

    if gross <= 0.0:
        return _copy_weights(weights)

    scale = float(config.target_gross) / gross
    return {ticker: float(weight) * scale for ticker, weight in weights.items()}


def size_positions(
    decision: Decision,
    vols: Dict[str, float] | None = None,
    config: PositionSizingConfig | None = None,
) -> Decision:
    config = config or PositionSizingConfig()

    base_weights = _validate_base_weights(decision)

    weights = _copy_weights(base_weights)
    decision.notes.append("Position sizing started from base_weights.")

    weights = _apply_volatility_scaling(weights, vols, config)
    decision.notes.append("Volatility scaling applied.")

    weights = _apply_conviction_scaling(weights, decision.conviction, config)
    decision.notes.append("Conviction scaling applied.")

    weights = _apply_asset_caps(weights, config)
    decision.notes.append(f"Per-asset caps applied with max_asset_weight={config.max_asset_weight}.")

    weights = _normalize_to_target_gross(weights, config)
    decision.notes.append(f"Gross target normalization applied with target_gross={config.target_gross}.")

    gross = _gross_exposure(weights)
    net = _net_exposure(weights)

    if gross == 0.0 and config.fallback_to_base_if_empty:
        weights = _copy_weights(base_weights)
        gross = _gross_exposure(weights)
        net = _net_exposure(weights)
        decision.notes.append("Sized weights collapsed to zero; fell back to base_weights.")

    decision.sized_weights = weights
    decision.gross_exposure = gross
    decision.net_exposure = net

    return decision