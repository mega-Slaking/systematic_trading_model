"""Shared FastAPI dependencies (spec §3.2).

Phase 0 exposes the settings dependency and a resolved DB-path dependency. The
cache handle (spec §5.2) arrives with the read endpoints that need it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends

from api.config import Settings, get_settings

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_db_path(settings: SettingsDep) -> Path:
    """Resolved SQLite path the API reads from (defaults to the engine's ``DB_PATH``)."""
    return settings.db_path


DbPathDep = Annotated[Path, Depends(get_db_path)]
