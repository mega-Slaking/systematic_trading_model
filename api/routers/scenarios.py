"""Scenarios router (spec endpoint 1).

The scenario picker + count for the app shell (replaces Streamlit's
``len(scenarios)`` line). Cheap ``SELECT DISTINCT`` read.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.scenario import ScenariosResponse
from api.services import scenarios as service

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=ScenariosResponse, summary="List persisted scenario ids")
def list_scenarios() -> ScenariosResponse:
    """Distinct persisted scenario ids (sorted) and their count."""
    return service.get_scenarios()
