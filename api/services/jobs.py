"""Backtest-job service (spec §5.1) -- in-process registry + subprocess worker.

Deliberately NOT a Celery/RQ/broker stack: single-analyst, single-node, and the
engine writes to one SQLite file, so backtests are serialized (a new job is
rejected with ``JobInProgressError`` -> 409 while one is queued/running).

The backtest runs in a **subprocess** (``api/backtest_worker.py``) rather than a
thread, so (a) the CPU-bound work doesn't GIL-starve the API, (b) it can stream
per-strategy progress over stdout, and (c) it can be cancelled by terminating the
process (safe: ``run_backtests`` only commits at the very end, so a killed run
leaves the DB at its pre-run state). On completion the analytics caches are
flushed (§5.2).

``_worker_command`` is module-level and overridable so tests drive a fast fake
worker instead of a real (minutes-long) backtest.
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

import json
import logging
import subprocess
import sys
import threading
import uuid
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from api.schemas.jobs import JobStatus

logger = logging.getLogger("api.jobs")

# Must match api/backtest_worker.py.
SENTINEL = "@@JOB@@"


class JobInProgressError(RuntimeError):
    """A backtest is already queued/running (the single-writer guard, §5.1)."""


def _known_strategy_names() -> set[str]:
    from src.strategy.presets import STRATEGIES

    return set(STRATEGIES)


def _worker_command(job_id: str, strategy_names: list[str] | None) -> list[str]:
    """Command that runs one backtest in a child process (overridable in tests)."""
    cmd = [sys.executable, "-m", "api.backtest_worker"]
    if strategy_names:
        cmd += list(strategy_names)
    return cmd


@dataclass
class _JobRecord:
    job_id: str
    status: str
    strategy_names: list[str] | None
    started_at: str | None = None
    finished_at: str | None = None
    scenario_ids_written: list[str] | None = None
    detail: str | None = None
    progress_current: int | None = None
    progress_total: int | None = None
    progress_strategy: str | None = None
    cancel_requested: bool = field(default=False, repr=False)
    process: "subprocess.Popen | None" = field(default=None, repr=False)
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
            progress_current=self.progress_current,
            progress_total=self.progress_total,
            progress_strategy=self.progress_strategy,
        )


_registry: dict[str, _JobRecord] = {}
_lock = threading.Lock()
# Single-slot executor: exactly one backtest subprocess is supervised at a time.
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
    """Supervise the backtest subprocess: spawn, stream progress, finalize."""
    with _lock:
        record = _registry[job_id]
        if record.cancel_requested:  # cancelled before it started
            record.status = "cancelled"
            record.finished_at = _now()
            return
        record.status = "running"
        record.started_at = _now()
        strategy_names = record.strategy_names

    result_ids: list[str] | None = None
    error_detail: str | None = None
    tail: deque[str] = deque(maxlen=25)

    try:
        proc = subprocess.Popen(
            _worker_command(job_id, strategy_names),
            cwd=str(_bootstrap.REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to launch backtest subprocess for job %s", job_id)
        with _lock:
            record = _registry[job_id]
            record.status = "error"
            record.detail = f"Failed to launch backtest process: {exc}"
            record.finished_at = _now()
        return

    with _lock:
        _registry[job_id].process = proc

    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        if line:
            tail.append(line)
        if not line.startswith(SENTINEL):
            continue
        try:
            msg = json.loads(line[len(SENTINEL):])
        except json.JSONDecodeError:
            continue
        kind = msg.get("type")
        if kind == "progress":
            with _lock:
                record = _registry[job_id]
                record.progress_current = msg.get("current")
                record.progress_total = msg.get("total")
                record.progress_strategy = msg.get("strategy")
        elif kind == "result":
            result_ids = list(msg.get("scenario_ids") or [])
        elif kind == "error":
            error_detail = msg.get("detail")

    code = proc.wait()

    with _lock:
        record = _registry[job_id]
        if record.cancel_requested:
            record.status = "cancelled"
        elif code == 0 and result_ids is not None:
            record.status = "done"
            record.scenario_ids_written = result_ids
        else:
            suffix = f"; last output: {' | '.join(tail)}" if tail else ""
            record.detail = error_detail or f"backtest exited with code {code}{suffix}"
            record.status = "error"
        record.finished_at = _now()
        final_status = record.status

    if final_status == "done":
        _flush_caches()


def submit_backtest_job(strategy_names: list[str] | None) -> JobStatus:
    """Validate + launch a backtest job. ``ValueError`` -> 422, ``JobInProgressError`` -> 409."""
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


def cancel_job(job_id: str) -> JobStatus:
    """Request cancellation; terminate the subprocess if it's running. 404 -> LookupError."""
    with _lock:
        record = _registry.get(job_id)
        if record is None:
            raise LookupError(job_id)
        if record.status not in ("queued", "running"):
            return record.to_status()  # already finished -- nothing to cancel
        record.cancel_requested = True
        proc = record.process

    if proc is not None and proc.poll() is None:
        proc.terminate()  # the worker thread flips status to "cancelled" on exit
    return get_job(job_id) or record.to_status()


def get_job(job_id: str) -> JobStatus | None:
    with _lock:
        record = _registry.get(job_id)
        return record.to_status() if record else None


def list_jobs() -> list[JobStatus]:
    with _lock:
        return [r.to_status() for r in _registry.values()]
