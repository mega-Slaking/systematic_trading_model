"""Strategies router (spec endpoint 12).

``GET`` introspects the ``STRATEGIES`` registry; ``POST /live`` selects which
entry the live run trades (runtime override) and ``POST /live/reset`` reverts to
the built-in default.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.strategy import SetLiveStrategyRequest, StrategiesResponse
from api.services import strategies as service

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=StrategiesResponse, summary="Strategy registry introspection")
def strategies() -> StrategiesResponse:
    """Flatten the ``STRATEGIES`` registry so the UI can decode scenario names."""
    return service.get_strategies()


@router.post("/live", response_model=StrategiesResponse, summary="Select the live strategy")
def set_live(request: SetLiveStrategyRequest) -> StrategiesResponse:
    """Make `request.name` the live book (override); unknown name -> 422."""
    try:
        return service.set_live_strategy(request.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/live/reset", response_model=StrategiesResponse, summary="Reset the live strategy to default")
def reset_live() -> StrategiesResponse:
    """Clear the override, reverting the live run to the LIVE_STRATEGY constant."""
    return service.reset_live_strategy()
