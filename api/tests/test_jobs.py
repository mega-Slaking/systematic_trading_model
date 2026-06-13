"""Tests for the backtest-job endpoints (13 + 14 + cancel), Phase 5/refinements.

The subprocess command is overridden (``jobs_service._worker_command``) to launch
a fast fake worker that emits the same ``@@JOB@@`` protocol, so the real
spawn/stream/cancel machinery is exercised without a minutes-long backtest.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

from fastapi.testclient import TestClient

from api.services import jobs as jobs_service

# Fake workers (run via `python -c <script>`), emitting the @@JOB@@ control lines.
_LIFECYCLE_SCRIPT = r"""
import json, sys
def e(p):
    sys.stdout.write("@@JOB@@" + json.dumps(p) + "\n"); sys.stdout.flush()
e({"type": "progress", "current": 0, "total": 2, "strategy": "a"})
e({"type": "progress", "current": 1, "total": 2, "strategy": "b"})
e({"type": "result", "scenario_ids": ["a", "b"]})
"""

_SLEEP_SCRIPT = r"""
import json, sys, time
sys.stdout.write("@@JOB@@" + json.dumps({"type": "progress", "current": 0, "total": 1, "strategy": "slow"}) + "\n")
sys.stdout.flush()
time.sleep(30)
sys.stdout.write("@@JOB@@" + json.dumps({"type": "result", "scenario_ids": ["slow"]}) + "\n")
sys.stdout.flush()
"""

_ERROR_SCRIPT = r"""
import json, sys
sys.stdout.write("@@JOB@@" + json.dumps({"type": "error", "detail": "boom in worker"}) + "\n")
sys.stdout.flush()
sys.exit(1)
"""


def _fake_cmd(script: str) -> Callable[[str, list[str] | None], list[str]]:
    return lambda job_id, names: [sys.executable, "-c", script]


def _wait_for(job_id: str, timeout: float = 20.0) -> None:
    record = jobs_service._registry.get(job_id)
    if record is not None and record.future is not None:
        record.future.result(timeout)


def _poll_until(client: TestClient, job_id: str, pred, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    body = client.get(f"/api/v1/jobs/{job_id}").json()
    while not pred(body) and time.monotonic() < deadline:
        time.sleep(0.05)
        body = client.get(f"/api/v1/jobs/{job_id}").json()
    return body


def test_lifecycle_streams_progress_then_done(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(jobs_service, "_worker_command", _fake_cmd(_LIFECYCLE_SCRIPT))
    resp = client.post("/api/v1/jobs/backtest", json={})
    assert resp.status_code == 202
    job = resp.json()
    assert job["status"] in ("queued", "running")

    _wait_for(job["job_id"])
    final = client.get(f"/api/v1/jobs/{job['job_id']}").json()
    assert final["status"] == "done"
    assert final["scenario_ids_written"] == ["a", "b"]
    # Progress was streamed from the subprocess.
    assert final["progress_total"] == 2
    assert final["progress_current"] == 1
    assert final["progress_strategy"] == "b"


def test_cancel_terminates_running_job(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(jobs_service, "_worker_command", _fake_cmd(_SLEEP_SCRIPT))
    job = client.post("/api/v1/jobs/backtest", json={}).json()
    # Wait until the subprocess is up and has emitted progress.
    _poll_until(client, job["job_id"], lambda b: b.get("progress_current") is not None)

    assert client.post(f"/api/v1/jobs/{job['job_id']}/cancel").status_code == 200
    _wait_for(job["job_id"], timeout=15)
    final = client.get(f"/api/v1/jobs/{job['job_id']}").json()
    assert final["status"] == "cancelled"


def test_error_status_from_failed_worker(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(jobs_service, "_worker_command", _fake_cmd(_ERROR_SCRIPT))
    job = client.post("/api/v1/jobs/backtest", json={}).json()
    _wait_for(job["job_id"])
    final = client.get(f"/api/v1/jobs/{job['job_id']}").json()
    assert final["status"] == "error"
    assert "boom in worker" in final["detail"]


def test_conflict_409_while_running(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(jobs_service, "_worker_command", _fake_cmd(_SLEEP_SCRIPT))
    job = client.post("/api/v1/jobs/backtest", json={}).json()
    _poll_until(client, job["job_id"], lambda b: b.get("progress_current") is not None)

    assert client.post("/api/v1/jobs/backtest", json={}).status_code == 409

    # Cleanup: cancel the running job and wait for it to finish.
    client.post(f"/api/v1/jobs/{job['job_id']}/cancel")
    _wait_for(job["job_id"], timeout=15)


def test_unknown_strategies_422(client: TestClient) -> None:
    resp = client.post("/api/v1/jobs/backtest", json={"strategy_names": ["not_a_strategy"]})
    assert resp.status_code == 422
    assert "Unknown strategies" in resp.json()["detail"]


def test_not_found_404(client: TestClient) -> None:
    assert client.get("/api/v1/jobs/does_not_exist").status_code == 404
    assert client.post("/api/v1/jobs/does_not_exist/cancel").status_code == 404
