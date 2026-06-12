"""Tests for the backtest-job endpoints (13 + 14), Phase 5.

The runner is stubbed (``jobs_service._runner``) so no real, minutes-long backtest
runs; we wait on the worker's future for deterministic assertions.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from api.services import jobs as jobs_service


def _wait_for(job_id: str, timeout: float = 10.0) -> None:
    """Block until the job's worker thread finishes (its future resolves)."""
    record = jobs_service._registry.get(job_id)
    if record is not None and record.future is not None:
        record.future.result(timeout)


def test_backtest_job_lifecycle(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs_service, "_runner", lambda names: ["scnA", "scnB"])

    resp = client.post("/api/v1/jobs/backtest", json={"strategy_names": None})
    assert resp.status_code == 202
    job = resp.json()
    assert job["status"] in ("queued", "running")

    _wait_for(job["job_id"])
    final = client.get(f"/api/v1/jobs/{job['job_id']}").json()
    assert final["status"] == "done"
    assert final["scenario_ids_written"] == ["scnA", "scnB"]
    assert final["started_at"] and final["finished_at"]


def test_backtest_job_unknown_strategies_422(client: TestClient) -> None:
    resp = client.post("/api/v1/jobs/backtest", json={"strategy_names": ["not_a_strategy"]})
    assert resp.status_code == 422
    assert "Unknown strategies" in resp.json()["detail"]


def test_backtest_job_conflict_409(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    gate = threading.Event()

    def slow_runner(_names):
        gate.wait(5)
        return ["x"]

    monkeypatch.setattr(jobs_service, "_runner", slow_runner)

    first = client.post("/api/v1/jobs/backtest", json={}).json()
    # A second submit while the first is still running is rejected.
    assert client.post("/api/v1/jobs/backtest", json={}).status_code == 409

    gate.set()
    _wait_for(first["job_id"])


def test_backtest_job_error_status(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_names):
        raise RuntimeError("backtest blew up")

    monkeypatch.setattr(jobs_service, "_runner", boom)

    job = client.post("/api/v1/jobs/backtest", json={}).json()
    _wait_for(job["job_id"])
    final = client.get(f"/api/v1/jobs/{job['job_id']}").json()
    assert final["status"] == "error"
    assert "blew up" in final["detail"]


def test_job_not_found_404(client: TestClient) -> None:
    assert client.get("/api/v1/jobs/does_not_exist").status_code == 404
