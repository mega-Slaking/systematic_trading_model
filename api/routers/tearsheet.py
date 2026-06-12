"""Tearsheet router (spec endpoint 5, Tab 3).

The one moderate-cost endpoint: ``build_tearsheet`` runs sub-second pandas and the
result is cached (§5.2). Run as a ``def`` handler so FastAPI offloads it to a
threadpool and a slow scenario can't block the event loop (§5.1). Domain errors
map to the §4.1 envelope: unknown scenario -> 404, bad input -> 422 (§10.9).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.schemas.tearsheet import TearsheetResponse
from api.services import tearsheet as service

router = APIRouter(prefix="/tearsheet", tags=["tearsheet"])


@router.get("/{scenario_id}", response_model=TearsheetResponse, summary="Full tearsheet for a scenario")
def tearsheet(
    scenario_id: str,
    risk_free_rate: float = Query(0.02, description="Annual risk-free rate (decimal)."),
    periods_per_year: int = Query(252, ge=1, description="Trading periods per year."),
) -> TearsheetResponse:
    """Metrics + equity/drawdown/rolling curves + exposure/regime/benchmark tables."""
    try:
        return service.get_tearsheet(scenario_id, risk_free_rate, periods_per_year)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
    except ValueError as exc:  # build_tearsheet's empty/missing-column/>1-scenario guard
        raise HTTPException(status_code=422, detail=str(exc))
