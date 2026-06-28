"""Lightweight timing instrumentation for benchmarks.

Two complementary tools:

- ``@timed(label)`` wraps a single coarse-grained call (e.g. a whole backtest
  run) and logs an ISO-8601 ``START`` / ``END`` line plus the elapsed seconds.
  Always active — the log lines are what you tail when a benchmark is left
  running in the background.

- ``@accumulate(label)`` sums elapsed time and call count across many fine-grained
  invocations (e.g. a covariance kernel called once per backtest date). It is a
  no-op unless the ``BENCH_TIMING`` environment variable is set, so production
  code paths pay only a single ``os.environ`` lookup per call. Read the totals
  with :func:`accumulated` and clear them with :func:`reset_accumulators`.

Both decorators are import-order safe and depend only on the standard library.
"""

from __future__ import annotations

import functools
import logging
import os
import time
from datetime import datetime

logger = logging.getLogger("bench.timing")

# label -> [total_seconds, n_calls]. Single-threaded use only (the backtest runs
# sequentially), so no locking is required.
_ACCUMULATORS: dict[str, list[float]] = {}


def _enabled() -> bool:
    """Whether accumulators record. Read at call time so import order never matters."""
    return bool(os.environ.get("BENCH_TIMING"))


def _now_iso() -> str:
    """Local-time ISO-8601 timestamp with millisecond precision."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def timed(label: str | None = None):
    """Log an ISO-timestamped START/END pair and the elapsed seconds for one call."""

    def decorator(fn):
        name = label or fn.__qualname__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            logger.info("[%s] START %s", _now_iso(), name)
            try:
                return fn(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                logger.info("[%s] END   %s  elapsed=%.4fs", _now_iso(), name, elapsed)

        return wrapper

    return decorator


def accumulate(label: str | None = None):
    """Sum elapsed time + call count for a hot function (only when ``BENCH_TIMING`` set)."""

    def decorator(fn):
        name = label or fn.__qualname__
        record = _ACCUMULATORS.setdefault(name, [0.0, 0.0])

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not _enabled():
                return fn(*args, **kwargs)
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                record[0] += time.perf_counter() - start
                record[1] += 1.0

        return wrapper

    return decorator


def accumulated() -> dict[str, tuple[float, int]]:
    """Snapshot of every accumulator as ``{label: (total_seconds, n_calls)}``."""
    return {name: (rec[0], int(rec[1])) for name, rec in _ACCUMULATORS.items()}


def reset_accumulators() -> None:
    """Zero every accumulator (call between independent timed runs)."""
    for rec in _ACCUMULATORS.values():
        rec[0] = 0.0
        rec[1] = 0.0
