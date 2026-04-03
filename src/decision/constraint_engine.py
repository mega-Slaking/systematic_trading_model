from __future__ import annotations

from typing import Dict, Optional

from src.decision.models import Decision
from src.decision.constraints import WeightConstraints, apply_constraints


def _resolve_constraint_input(decision: Decision) -> tuple[Dict[str, float], str]:
    if decision.sized_weights is not None:
        return dict(decision.sized_weights), "sized_weights"

    if decision.base_weights is not None:
        return dict(decision.base_weights), "base_weights"

    raise ValueError(
        "Decision must have sized_weights or base_weights before final constraints."
    )


def _gross_exposure(weights: Dict[str, float]) -> float:
    return sum(abs(float(w)) for w in weights.values())


def _net_exposure(weights: Dict[str, float]) -> float:
    return sum(float(w) for w in weights.values())


def apply_final_constraints(
    decision: Decision,
    constraints: Optional[WeightConstraints] = None,
) -> Decision:
    """
    Apply hard portfolio constraints to the latest available target weights.

    This stage is intended to convert:
    - sized_weights -> final_weights
    or, if sizing has not been run,
    - base_weights -> final_weights
    """
    constraints = constraints or WeightConstraints()

    raw_weights, source = _resolve_constraint_input(decision)

    final_weights = apply_constraints(raw_weights, constraints)

    decision.final_weights = final_weights

    # Recompute exposures on final weights so downstream execution can rely on them.
    decision.gross_exposure = _gross_exposure(final_weights)
    decision.net_exposure = _net_exposure(final_weights)

    decision.notes.append(
        f"Final portfolio constraints applied using {source} as input."
    )

    if constraints.eligible is not None:
        decision.notes.append("Eligibility filter applied in constraint stage.")

    if constraints.shy_floor > 0.0:
        decision.notes.append(
            f"SHY floor enforced at {constraints.shy_floor:.4f}."
        )

    return decision