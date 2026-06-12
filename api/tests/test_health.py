"""Tests for the ``/health`` probe and the OpenAPI surface (Phase 0)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.config import Settings, get_settings
from api.main import create_app


def test_health_ok_with_real_db(client: TestClient) -> None:
    """Against the default DB_PATH (the populated repo DB), health is ``ok``."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"status", "db_exists", "db_path", "api_version"}
    # The repo ships a populated data/database.db; if present, status must be ok.
    assert body["db_exists"] is True
    assert body["status"] == "ok"
    assert body["api_version"]


def test_health_degraded_when_db_missing(tmp_path) -> None:
    """With an overridden, non-existent DB path, health reports ``degraded`` (still 200)."""
    missing = tmp_path / "nope.db"
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(db_path=missing)
    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["db_exists"] is False
        assert body["status"] == "degraded"
        assert body["db_path"].endswith("nope.db")
    finally:
        app.dependency_overrides.clear()


def test_openapi_and_docs_available(client: TestClient) -> None:
    """The OpenAPI schema and Swagger UI are served (needed for frontend type-gen)."""
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    assert "/api/v1/health" in paths

    docs = client.get("/docs")
    assert docs.status_code == 200


# Phase 0 guard, superseded by Phase 1 (which adds the /etf-prices endpoints).
# Kept commented per repo convention (comment, don't delete); re-enabling it would
# now correctly fail, since business endpoints exist.
# def test_only_health_endpoint_exists(client: TestClient) -> None:
#     """Phase 0 guard: no business endpoints are wired yet -- only /health under /api/v1."""
#     paths = client.get("/openapi.json").json()["paths"]
#     business = [p for p in paths if p.startswith("/api/v1") and p != "/api/v1/health"]
#     assert business == [], f"unexpected non-health endpoints present: {business}"


def test_expected_endpoints_registered(client: TestClient) -> None:
    """The OpenAPI surface exposes the currently-shipped endpoints (health + Phases 1-2)."""
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/v1/health",
        "/api/v1/scenarios",
        "/api/v1/backtest-results/nav-comparison",
        "/api/v1/backtest-results/returns",
        "/api/v1/backtest-results/{scenario_id}/daily",
        "/api/v1/tearsheet/{scenario_id}",
        "/api/v1/etf-prices",
        "/api/v1/etf-prices/stats",
        "/api/v1/volatility-features",
        "/api/v1/volatility-features/latest",
        "/api/v1/macro",
        "/api/v1/macro/yield-curve",
        "/api/v1/strategies",
    ):
        assert path in paths, f"missing endpoint: {path}"
