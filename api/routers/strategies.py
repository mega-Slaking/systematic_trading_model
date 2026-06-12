"""Strategies router (spec endpoint 12) -- read-only registry introspection."""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.strategy import StrategiesResponse
from api.services import strategies as service

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=StrategiesResponse, summary="Strategy registry introspection")
def strategies() -> StrategiesResponse:
    """Flatten the ``STRATEGIES`` registry so the UI can decode scenario names."""
    return service.get_strategies()
