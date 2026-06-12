"""Backtest-job service (spec §5.1) -- in-process registry + single-slot executor.

Deliberately NOT a Celery/RQ/broker stack: this is a single-analyst, single-node
tool, and the engine writes to one SQLite file, so backtests must be serialized.
A ``ThreadPoolExecutor(max_workers=1)`` is that single writer; a new job is
rejected (``JobInProgressError`` -> 409) while one is queued/running. On
completion the analytics caches are flushed (§5.2). The runner is module-level and
overridable so tests never run a real (minutes-long) backtest.

Upgrade path: swap the registry/executor for RQ/Celery + Redis behind this same
two-function contract if it ever goes multi-user.
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from api.schemas.jobs import JobStatus

logger = logging.getLogger("api.jobs")


class JobInProgressError(RuntimeError):
    """A backtest is already queued/running (the single-writer guard, §5.1)."""


def _known_strategy_names() -> set[str]:
    from src.strategy.presets import STRATEGIES

    return set(STRATEGIES)


def _default_runner(strategy_names: list[str] | None) -> list[str]:
    """Run the real backtest (lazy import -- the engine is heavy)."""
    from run_backtest import run_backtests

    return run_backtests(strategy_names)


# Overridable so tests inject a fast stub instead of a real backtest.
_runner = _default_runner


@dataclass
class _JobRecord:
    job_id: str
    status: str
    strategy_names: list[str] | None
    started_at: str | None = None
    finished_at: str | None = None
    scenario_ids_written: list[str] | None = None
    detail: str | None = None
    future: Future | None = field(default=None, repr=False)

    def to_status(self) -> JobStatus:
        return JobStatus(
            job_id=self.job_id,
            status=self.status,
            strategy_names=self.strategy_names,
            started_at=self.started_at,
            finished_at=self.finished_at,
            scenario_ids_written=self.scenario_ids_written,
            detail=self.detail,
        )


_registry: dict[str, _JobRecord] = {}
_lock = threading.Lock()
# Single-slot executor: exactly one backtest runs at a time (one SQLite writer).
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backtest-job")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flush_caches() -> None:
    """Invalidate analytics caches so a finished run is reflected at once (§5.2)."""
    try:
        from api.services.tearsheet import flush_cache

        flush_cache()
    except Exception:  # noqa: BLE001 -- never let cache flushing fail a completed job
        logger.exception("Cache flush after backtest failed")


def _worker(job_id: str) -> None:
    with _lock:
        record = _registry[job_id]
        record.status = "running"
        record.started_at = _now()
        strategy_names = record.strategy_names

    try:
        written = _runner(strategy_names)
        with _lock:
            record = _registry[job_id]
            record.status = "done"
            record.finished_at = _now()
            record.scenario_ids_written = list(written)
        _flush_caches()
    except Exception as exc:  # noqa: BLE001 -- surface as job error, not a crash
        logger.exception("Backtest job %s failed", job_id)
        with _lock:
            record = _registry[job_id]
            record.status = "error"
            record.finished_at = _now()
            record.detail = str(exc)


def submit_backtest_job(strategy_names: list[str] | None) -> JobStatus:
    """Validate + launch a backtest job.

    Raises ``ValueError`` for unknown strategy names (router -> 422) and
    ``JobInProgressError`` if one is already active (router -> 409).
    """
    if strategy_names:
        unknown = sorted(set(strategy_names) - _known_strategy_names())
        if unknown:
            raise ValueError(f"Unknown strategies: {unknown}")

    with _lock:
        if any(r.status in ("queued", "running") for r in _registry.values()):
            raise JobInProgressError("A backtest is already running.")
        job_id = uuid.uuid4().hex[:12]
        record = _JobRecord(job_id=job_id, status="queued", strategy_names=strategy_names)
        _registry[job_id] = record
        record.future = _executor.submit(_worker, job_id)
        return record.to_status()


def get_job(job_id: str) -> JobStatus | None:
    with _lock:
        record = _registry.get(job_id)
        return record.to_status() if record else None


def list_jobs() -> list[JobStatus]:
    with _lock:
        return [r.to_status() for r in _registry.values()]
