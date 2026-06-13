"""Subprocess entry point for a backtest job (cancel / progress / responsiveness).

Run as ``python -m api.backtest_worker [strategy_name ...]`` (no args = whole
registry). It runs the backtest in its **own process** so the CPU-bound work
doesn't GIL-starve the API, and streams control messages to stdout as lines:

    @@JOB@@{"type": "progress", "current": 3, "total": 18, "strategy": "..."}
    @@JOB@@{"type": "result", "scenario_ids": [...]}
    @@JOB@@{"type": "error", "detail": "..."}

``api/services/jobs.py`` spawns this, parses those lines to update the job
record, waits for exit, and can ``terminate()`` the process to cancel a run
(safe: ``run_backtests`` only commits at the very end, so a killed run leaves the
DB at its pre-run state).
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path so `run_backtest` / `src.*`
# resolve regardless of how the subprocess was launched (spec §3.3).
from api import _bootstrap  # noqa: F401

import json
import sys

SENTINEL = "@@JOB@@"


def _emit(payload: dict) -> None:
    """Write one control line to stdout, flushed so the parent reads it live."""
    sys.stdout.write(SENTINEL + json.dumps(payload) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    strategy_names = argv or None
    try:
        from run_backtest import run_backtests

        def on_progress(completed: int, total: int, strategy: str) -> None:
            _emit({"type": "progress", "current": completed, "total": total, "strategy": strategy})

        written = run_backtests(strategy_names, on_progress=on_progress)
        _emit({"type": "result", "scenario_ids": list(written)})
        return 0
    except Exception as exc:  # noqa: BLE001 -- report as a job error, not a traceback dump
        _emit({"type": "error", "detail": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
