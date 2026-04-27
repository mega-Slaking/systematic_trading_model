from dataclasses import dataclass
from typing import Dict

from src.covariance.estimator import compute_portfolio_vol_from_covariance
from src.decision.models import Decision
from src.volatility.models import VolatilityEstimate
from src.covariance.models import CovarianceEstimate


TARGET_TICKERS = ["TLT", "AGG", "SHY"]


@dataclass
class PositionSizingConfig:
    target_gross: float = 1.0
    min_vol: float = 0.05
    max_asset_weight: float = 1.0
    use_vol_scaling: bool = True
    fallback_to_base_if_empty: bool = True
    vol_scaling_power: float = 0.20 #lower value - more signal based, higher - more risk adjusted
    use_covariance_scaling: bool = True
    target_portfolio_vol: float = 0.10
    starting_weight_source: str = "conviction"


def _extract_weight_vector(
    source_name: str,
    weights_dict: dict[str, float] | None,
) -> Dict[str, float]:
    if weights_dict is None:
        raise ValueError(f"{source_name} is None.")

    weights = {
        ticker: float(weights_dict.get(ticker, 0.0))
        for ticker in TARGET_TICKERS
    }

    if not any(weight != 0.0 for weight in weights.values()):
        raise ValueError(f"{source_name} is empty or all zero.")

    return weights

def _get_starting_weights(decision: Decision, config: PositionSizingConfig) -> Dict[str, float]:
    source = config.starting_weight_source

    if source == "legacy":
        weights = _extract_weight_vector(
            "decision.legacy_base_weights",
            decision.legacy_base_weights,
        )
        decision.notes.append("Position sizing started from legacy_base_weights.")
        return weights

    if source == "conviction":
        if decision.conviction_weights is not None:
            weights = _extract_weight_vector(
                "decision.conviction_weights",
                decision.conviction_weights,
            )
            decision.notes.append("Position sizing started from conviction_weights.")
            return weights

        if config.fallback_to_base_if_empty:
            weights = _extract_weight_vector(
                "decision.base_weights",
                decision.base_weights,
            )
            decision.notes.append(
                "conviction_weights unavailable; position sizing fell back to base_weights."
            )
            return weights

        raise ValueError(
            "starting_weight_source='conviction' but conviction_weights is unavailable."
        )

    raise ValueError(f"Unknown starting_weight_source: {source}")


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
        if weight == 0.0:
            scaled[ticker] = 0.0
            continue

        vol = vols.get(ticker)

        if vol is None:
            scaled[ticker] = float(weight)
            continue

        effective_vol = max(float(vol), config.min_vol)
        scaled[ticker] = float(weight) / (effective_vol ** config.vol_scaling_power)

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


def _apply_covariance_scaling_with_shy_buffer(
    weights: Dict[str, float],
    cov_estimate: CovarianceEstimate | None,
    config: PositionSizingConfig,
) -> tuple[Dict[str, float], float | None, float]:
    if not config.use_covariance_scaling:
        return _copy_weights(weights), None, 1.0

    if cov_estimate is None:
        return _copy_weights(weights), None, 1.0

    portfolio_vol = compute_portfolio_vol_from_covariance(weights, cov_estimate)
    if portfolio_vol is None or portfolio_vol <= 0.0:
        return _copy_weights(weights), portfolio_vol, 1.0

    raw_scale = float(config.target_portfolio_vol) / float(portfolio_vol)

    adjusted = _copy_weights(weights)

    risky_tickers = [ticker for ticker in adjusted if ticker != "SHY"]
    risky_gross = sum(abs(float(adjusted[ticker])) for ticker in risky_tickers)

    if risky_gross <= 0.0:
        return adjusted, portfolio_vol, 1.0

    max_scale = float(config.target_gross) / risky_gross
    scale = min(raw_scale, max_scale)

    for ticker in risky_tickers:
        adjusted[ticker] = float(adjusted[ticker]) * scale

    scaled_risky_gross = sum(abs(float(adjusted[ticker])) for ticker in risky_tickers)
    adjusted["SHY"] = max(0.0, float(config.target_gross) - scaled_risky_gross)

    return adjusted, portfolio_vol, scale


def size_positions(
    decision: Decision,
    vol_estimate: VolatilityEstimate | None = None,
    cov_estimate: CovarianceEstimate | None = None,
    config: PositionSizingConfig | None = None,
) -> Decision:
    config = config or PositionSizingConfig()

    starting_weights = _get_starting_weights(decision, config)
    vols = vol_estimate.vols if vol_estimate else None

    weights = _copy_weights(starting_weights)

    weights = _apply_volatility_scaling(weights, vols, config)
    decision.notes.append("Volatility scaling applied.")

    weights = _apply_asset_caps(weights, config)
    decision.notes.append(f"Per-asset caps applied with max_asset_weight={config.max_asset_weight}.")

    weights = _normalize_to_target_gross(weights, config)
    decision.notes.append(f"Gross target normalization applied with target_gross={config.target_gross}.")

    weights, portfolio_vol, portfolio_scale = _apply_covariance_scaling_with_shy_buffer(
        weights,
        cov_estimate,
        config,
    )

    decision.portfolio_vol_estimate = portfolio_vol
    decision.portfolio_vol_target = config.target_portfolio_vol if config.use_covariance_scaling else None
    decision.portfolio_scale = portfolio_scale

    if config.use_covariance_scaling:
        decision.notes.append(
            f"Covariance scaling applied with portfolio_vol={portfolio_vol} and scale={portfolio_scale}."
        )

    gross = _gross_exposure(weights)
    net = _net_exposure(weights)

    if gross == 0.0 and config.fallback_to_base_if_empty:
        weights = _copy_weights(starting_weights)
        gross = _gross_exposure(weights)
        net = _net_exposure(weights)
        decision.notes.append("Sized weights collapsed to zero; fell back to conviction_weights.")

    decision.sized_weights = weights
    decision.gross_exposure = gross
    decision.net_exposure = net

    return decision