from dataclasses import dataclass
from typing import Dict, Iterable

from src.utils.weights import clip_weights, normalize_weights


@dataclass(frozen=True)
class WeightConstraints:
    # Optional caps/floors per asset
    min_w: Dict[str, float] | None = None
    max_w: Dict[str, float] | None = None

    # Optional cash buffer: keep some weight in SHY (or in cash if you model cash explicitly)
    # Here we implement it as "ensure at least shy_floor" as a simple cash-like buffer.
    shy_floor: float = 0.0

    # If some tickers are not eligible today (missing price, stale data),
    # they get forced to 0 and we renormalize.
    eligible: Iterable[str] | None = None

    # Fallback asset if everything collapses to zero
    fallback_ticker: str = "SHY"


def apply_constraints(
    raw_weights: Dict[str, float],
    constraints: WeightConstraints,
) -> Dict[str, float]:
    w = dict(raw_weights)

    # 1) Eligibility filter
    if constraints.eligible is not None:
        eligible_set = set(constraints.eligible)
        for k in list(w.keys()):
            if k not in eligible_set:
                w[k] = 0.0

    # 2) Enforce SHY floor (simple cash-buffer proxy)
    if constraints.shy_floor > 0.0:
        w["SHY"] = max(float(w.get("SHY", 0.0)), float(constraints.shy_floor))

    # 3) Clip by min/max
    w = clip_weights(w, min_w=constraints.min_w, max_w=constraints.max_w)

    # 4) Normalize to sum to 1
    w = normalize_weights(w)

    # 5) Fallback if normalization collapsed to all zeros
    if sum(w.values()) <= 0.0:
        w = {k: 0.0 for k in raw_weights.keys()}
        w[constraints.fallback_ticker] = 1.0

    #Can add other hard rules as according

    return w
