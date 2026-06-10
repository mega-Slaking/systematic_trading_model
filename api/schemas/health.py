"""Health-probe schema (spec endpoint #0)."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """DB-exists gate -- replaces the Streamlit ``app.py`` ``DB_PATH.exists()`` check.

    ``status`` is ``"ok"`` only when the configured SQLite DB file is present and
    readable. The React ``HealthGate`` blocks the app on anything else.
    """

    status: str  # "ok" | "degraded"
    db_exists: bool
    db_path: str
    api_version: str
