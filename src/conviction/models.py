from dataclasses import dataclass, field


@dataclass
class ConvictionConfig:
    """
    Controls how strongly conviction tilts base weights.

    Conviction is not a regime allocation table.
    It scores asset-level signal overlap using:
    - macro evidence
    - price confirmation
    - favourable-asset direction prior
    """

    min_multiplier: float = 0.50
    max_multiplier: float = 1.50

    macro_weight: float = 0.50
    price_weight: float = 0.40
    direction_weight: float = 0.10

    multiplier_sensitivity: float = 0.70

    use_price_fallback: bool = True


@dataclass
class ConvictionEstimate:

    as_of_date: str
    conviction: dict[str, float]
    raw_scores: dict[str, float]
    component_scores: dict[str, dict[str, float]]
    notes: list[str] = field(default_factory=list)