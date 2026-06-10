"""API settings via ``pydantic-settings`` (spec §8).

The analytics API is read-only over SQLite and needs **no secrets** -- it does
not import ``config.py`` / ``FRED_API_KEY`` or any fetch path. Settings here
cover only host/port, CORS origins, cache TTLs and a ``DB_PATH`` override.

The default DB location is ``src/storage/paths.py:DB_PATH`` (the single source of
truth), resolved against the repo root so the API agrees with the engine on the
DB location regardless of the process CWD.
"""

from __future__ import annotations

# Side-effect import: puts the repo root and src/ on sys.path before the
# ``src.storage.paths`` import below can run. Keep this first.
from api import _bootstrap

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.storage.paths import DB_PATH as _ENGINE_DB_PATH


def _default_db_path() -> Path:
    """Resolve the engine's ``DB_PATH`` against the repo root.

    ``src.storage.paths.DB_PATH`` is the relative ``Path("data/database.db")``;
    the engine relies on being launched from the repo root. We anchor it to the
    repo root explicitly so ``/health`` reports correctly no matter where uvicorn
    was started from, while still treating ``DB_PATH`` as the single source.
    """
    if _ENGINE_DB_PATH.is_absolute():
        return _ENGINE_DB_PATH
    return (_bootstrap.REPO_ROOT / _ENGINE_DB_PATH).resolve()


class Settings(BaseSettings):
    """Runtime configuration, overridable via env vars / ``.env`` (prefix ``API_``)."""

    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- service ---
    api_title: str = "Systematic Trading Analytics API"
    api_version: str = "1.12.0"
    api_v1_prefix: str = "/api/v1"

    # --- network ---
    host: str = "127.0.0.1"
    port: int = 8000

    # CORS allow-list. Dev: the Vite dev server. Local-only deploy (spec §8/§10);
    # production hardening (non-`*` origins, TLS) is a later concern.
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # --- data ---
    db_path: Path = _default_db_path()

    # --- caching (consumed by later phases; defined now so the contract is stable) ---
    read_cache_ttl_seconds: int = 45
    tearsheet_cache_ttl_seconds: int = 300

    @field_validator("db_path", mode="before")
    @classmethod
    def _coerce_db_path(cls, value: object) -> object:
        """Allow ``API_DB_PATH`` to be supplied as a string in the environment."""
        if isinstance(value, str) and value:
            return Path(value)
        return value


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a process-wide cached ``Settings`` (FastAPI dependency-friendly)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
