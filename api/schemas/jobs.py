"""Backtest-job schemas (spec endpoints 13 + 14, Phase 5).

The optional backtest-from-UI trigger. v1 was read-only; this adds the single
write path behind the unchanged two-endpoint contract (§5.1).
"""

from __future__ import annotations

from pydantic import BaseModel


class BacktestJobRequest(BaseModel):
    """Trigger body: an optional subset of strategy names (``None`` = whole registry)."""

    strategy_names: list[str] | None = None


class JobStatus(BaseModel):
    """A backtest job's state (polled via ``GET /jobs/{job_id}``)."""

    job_id: str
    status: str  # queued | running | done | error | cancelled
    strategy_names: list[str] | None
    started_at: str | None
    finished_at: str | None
    scenario_ids_written: list[str] | None
    detail: str | None
    # Per-strategy progress streamed from the subprocess (null until it starts).
    progress_current: int | None
    progress_total: int | None
    progress_strategy: str | None
