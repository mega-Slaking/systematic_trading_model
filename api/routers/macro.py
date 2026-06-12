"""Macro router (spec endpoints 10 + 11, Page 6)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas.macro import MacroResponse, YieldCurveResponse
from api.services import macro as service

router = APIRouter(prefix="/macro", tags=["macro"])


def _split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    return parts or None


@router.get("", response_model=MacroResponse, summary="Macro indicator series")
def macro(
    indicators: str | None = Query(None, description="Comma-separated indicator keys. Default: all."),
) -> MacroResponse:
    """One series per requested macro indicator (each on its own date axis)."""
    return service.get_macro(_split_csv(indicators))


@router.get("/yield-curve", response_model=YieldCurveResponse, summary="10Y/2Y yields + spread")
def yield_curve() -> YieldCurveResponse:
    """10Y and 2Y yields plus the 10Y-2Y spread."""
    return service.get_yield_curve()
