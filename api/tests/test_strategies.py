"""Tests for the strategies introspection endpoint (12), Phase 4."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_strategies_introspection(client: TestClient) -> None:
    body = client.get("/api/v1/strategies").json()
    live = body["live_strategy"]
    strategies = body["strategies"]
    names = {s["name"] for s in strategies}

    assert len(strategies) > 0
    assert "default" in names
    # The live strategy is a real registry entry, flagged on exactly one summary.
    assert live in names
    flagged = [s for s in strategies if s["is_live"]]
    assert len(flagged) == 1 and flagged[0]["name"] == live

    default = next(s for s in strategies if s["name"] == "default")
    assert isinstance(default["use_vol_scaling"], bool)
    assert isinstance(default["use_covariance_scaling"], bool)
    assert isinstance(default["target_portfolio_vol"], (int, float))
    assert default["cov_method"]
    assert default["starting_weight_source"]
