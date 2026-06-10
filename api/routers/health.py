"""Health probe (spec endpoint #0).

DB-exists gate that replaces the Streamlit ``app.py`` ``DB_PATH.exists()`` guard.
The React ``HealthGate`` blocks the SPA until this returns ``status == "ok"``.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import DbPathDep, SettingsDep
from api.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="DB-exists health gate")
def health(db_path: DbPathDep, settings: SettingsDep) -> HealthResponse:
    """Report whether the configured SQLite DB is present.

    Always HTTP 200 so the client can read the body and decide; ``status`` is
    ``"ok"`` only when the DB file exists, otherwise ``"degraded"``.
    """
    exists = db_path.is_file()
    return HealthResponse(
        status="ok" if exists else "degraded",
        db_exists=exists,
        db_path=str(db_path),
        api_version=settings.api_version,
    )
