"""Scenarios service (spec endpoint 1).

Thin wrapper over ``src/storage/db_reader.py:get_scenario_ids`` -- the distinct
persisted scenario tags, sorted.
"""

from __future__ import annotations

# Side-effect import: repo root + src/ on sys.path (spec §3.3). Idempotent.
from api import _bootstrap  # noqa: F401

from src.storage.db_reader import get_scenario_ids

from api.schemas.scenario import ScenariosResponse


def get_scenarios() -> ScenariosResponse:
    """Distinct persisted scenario ids (sorted) and their count."""
    ids = sorted(get_scenario_ids())
    return ScenariosResponse(scenarios=ids, count=len(ids))
