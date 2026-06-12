"""Volatility-features router (spec endpoints 8 + 9, Tab 5)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from api.schemas.volatility import VolatilityFeaturesResponse, VolatilityLatestResponse
from api.services import volatility as service

router = APIRouter(prefix="/volatility-features", tags=["volatility"])


def _split_csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None


@router.get("", response_model=VolatilityFeaturesResponse, summary="Vol estimate lines for a ticker")
def volatility_features(
    ticker: str = Query(..., description="Ticker, e.g. TLT (required)."),
    methods: str | None = Query(None, description="Comma-separated method keys. Default: all available."),
) -> VolatilityFeaturesResponse:
    """Per-method annualized-vol lines for one ticker (Tab 5 chart)."""
    return service.get_volatility_for_ticker(ticker.upper(), _split_csv(methods))


@router.get("/latest", response_model=VolatilityLatestResponse, summary="Latest vol per ticker")
def volatility_latest() -> VolatilityLatestResponse:
    """Latest annualized vol per method per ticker (Tab 5 table)."""
    return service.get_volatility_latest()
