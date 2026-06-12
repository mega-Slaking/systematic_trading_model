"""FastAPI application entry point.

Phase 0 scaffold (spec §9): app + CORS + ``pydantic-settings`` + the ``/health``
probe only. No business endpoints yet. Run from the repo root with::

    uvicorn api.main:app --reload --port 8000

which serves ``/api/v1/health``, ``/docs`` (Swagger UI) and ``/openapi.json``.
"""

from __future__ import annotations

# Side-effect import: puts the repo root and src/ on sys.path before any
# ``src.*`` / ``accounting.*`` import resolves (spec §3.3). Keep this first.
from api import _bootstrap  # noqa: F401  (imported for its sys.path side effect)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from api.config import get_settings
from api.routers import (
    backtest_results,
    etf_prices,
    health,
    macro,
    scenarios,
    strategies,
    tearsheet,
    volatility,
)
from api.schemas.common import ErrorResponse


def create_app() -> FastAPI:
    """Build and configure the FastAPI application (factory form, eases testing)."""
    settings = get_settings()

    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        # orjson gives fast float serialization AND a NaN safety net (spec §6).
        # The §6 sanitizer in serialization/frames.py is the *primary* guarantee
        # of valid JSON. But the encoder choice is load-bearing for the bypass
        # case: verified on these pins (FastAPI 0.136.3 / Py 3.14) that a raw
        # non-finite float reaching a model field renders as a safe `null` under
        # ORJSONResponse, whereas FastAPI's default (stdlib json) path raises
        # ValueError -> HTTP 500. So orjson is kept deliberately as defense-in-
        # depth. (FastAPI 0.136 emits a cosmetic DeprecationWarning saying a
        # custom response class is "not required"; we keep it on purpose for the
        # null-degradation behavior, and filter that one warning in the test cfg.)
        default_response_class=ORJSONResponse,
    )

    # CORS: the Vite dev server and the API are different origins (spec §8).
    # Local-only for v1; production hardening (non-`*` origins, TLS) is deferred.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Consistent error envelope (spec §4.1). Domain handlers (404/422/503) land
    # with the endpoints that raise them; this is the generic fallback so an
    # unexpected error still returns the documented shape rather than a raw 500
    # body -- without leaking a stack trace (logged server-side instead).
    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> ORJSONResponse:
        import logging

        logging.getLogger("api").exception("Unhandled error on %s %s", request.method, request.url.path)
        return ORJSONResponse(
            status_code=500,
            content=ErrorResponse(detail="Internal server error", code="INTERNAL_ERROR").model_dump(),
        )

    # Routers, all under the versioned base path (spec §4.1).
    app.include_router(health.router, prefix=settings.api_v1_prefix)
    app.include_router(scenarios.router, prefix=settings.api_v1_prefix)
    app.include_router(backtest_results.router, prefix=settings.api_v1_prefix)
    app.include_router(tearsheet.router, prefix=settings.api_v1_prefix)
    app.include_router(etf_prices.router, prefix=settings.api_v1_prefix)
    app.include_router(volatility.router, prefix=settings.api_v1_prefix)
    app.include_router(macro.router, prefix=settings.api_v1_prefix)
    app.include_router(strategies.router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
