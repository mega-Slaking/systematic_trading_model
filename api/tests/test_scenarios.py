"""Tests for the scenarios endpoint (1, Phase 2), against the populated repo DB."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_scenarios_lists_sorted_persisted_ids(client: TestClient) -> None:
    resp = client.get("/api/v1/scenarios")
    assert resp.status_code == 200
    body = resp.json()
    scenarios = body["scenarios"]
    assert len(scenarios) > 0
    assert body["count"] == len(scenarios)
    assert scenarios == sorted(scenarios)
    # §2.6: the persisted set is the baseV1_* grid plus the live-equivalent "default".
    assert "default" in scenarios
