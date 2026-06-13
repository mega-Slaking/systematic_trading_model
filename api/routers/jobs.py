"""Backtest-job router (spec endpoints 13 + 14, Phase 5).

``POST /jobs/backtest`` launches a run and returns ``202`` with the job; the
client polls ``GET /jobs/{job_id}`` until ``done``/``error``. Unknown strategy
names -> 422; an already-running backtest -> 409 (single-writer guard).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.jobs import BacktestJobRequest, JobStatus
from api.services import jobs as service
from api.services.jobs import JobInProgressError

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/backtest", status_code=202, response_model=JobStatus, summary="Trigger a backtest run")
def trigger_backtest(request: BacktestJobRequest) -> JobStatus:
    """Launch a backtest over the registry (or a subset); returns 202 + the job."""
    try:
        return service.submit_backtest_job(request.strategy_names)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except JobInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("", response_model=list[JobStatus], summary="List backtest jobs")
def list_jobs() -> list[JobStatus]:
    """All jobs this process has seen (in-process registry)."""
    return service.list_jobs()


@router.get("/{job_id}", response_model=JobStatus, summary="Poll a backtest job")
def job_status(job_id: str) -> JobStatus:
    """Status of one job; 404 if the id is unknown to this process."""
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@router.post("/{job_id}/cancel", response_model=JobStatus, summary="Cancel a running backtest")
def cancel_job(job_id: str) -> JobStatus:
    """Terminate a queued/running job's subprocess; a no-op if it already finished."""
    try:
        return service.cancel_job(job_id)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
