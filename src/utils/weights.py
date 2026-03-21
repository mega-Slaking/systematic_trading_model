from typing import Dict


def normalize_weights(weights: Dict[str, float], eps: float = 1e-12) -> Dict[str, float]:
    cleaned: Dict[str, float] = {}
    for k, v in weights.items():
        try:
            fv = float(v)
        except Exception:
            fv = 0.0
        if fv != fv:  # NaN check
            fv = 0.0
        if fv < 0.0:
            fv = 0.0
        cleaned[k] = fv

    total = sum(cleaned.values())
    if total <= eps:
        return {k: 0.0 for k in cleaned.keys()}

    return {k: v / total for k, v in cleaned.items()}


def clip_weights(
    weights: Dict[str, float],
    min_w: Dict[str, float] | None = None,
    max_w: Dict[str, float] | None = None,
) -> Dict[str, float]:
    min_w = min_w or {}
    max_w = max_w or {}

    out: Dict[str, float] = {}
    for k, v in weights.items():
        lo = float(min_w.get(k, 0.0))
        hi = float(max_w.get(k, 1.0))
        fv = float(v)

        if fv < lo:
            fv = lo
        if fv > hi:
            fv = hi

        out[k] = fv
    return out


def drift_l1(current: Dict[str, float], target: Dict[str, float]) -> float:
    keys = set(current.keys()) | set(target.keys())
    return sum(abs(float(target.get(k, 0.0)) - float(current.get(k, 0.0))) for k in keys)


def turnover_l1(prev: Dict[str, float], new: Dict[str, float]) -> float:
    # Standard definition: 0.5 * sum(|Δw|)
    return 0.5 * drift_l1(prev, new)
