"""Tests for the strategies introspection + live-selection endpoints (12)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def isolated_override(tmp_path, monkeypatch):
    """Point the live-strategy override file at a temp path so tests never touch
    the real ``data/live_strategy.json`` (the functions read the module global
    at call time, so patching the attribute is enough). Returns the path so tests
    can plant a hand-crafted/malformed file."""
    path = tmp_path / "live_strategy.json"
    monkeypatch.setattr("src.strategy.presets._OVERRIDE_PATH", path)
    return path


def test_strategies_introspection(client: TestClient, isolated_override) -> None:
    body = client.get("/api/v1/strategies").json()
    live = body["live_strategy"]
    strategies = body["strategies"]
    names = {s["name"] for s in strategies}

    assert len(strategies) > 0
    assert "default" in names
    # No override set -> effective live == the built-in default constant.
    assert live == body["default_strategy"]
    assert body["is_overridden"] is False
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


def test_set_and_reset_live_strategy(client: TestClient, isolated_override) -> None:
    base = client.get("/api/v1/strategies").json()
    default_name = base["default_strategy"]
    # Pick any registry entry that is NOT the current default to prove the flip.
    target = next(s["name"] for s in base["strategies"] if s["name"] != default_name)

    # Select it as live.
    set_body = client.post("/api/v1/strategies/live", json={"name": target}).json()
    assert set_body["live_strategy"] == target
    assert set_body["default_strategy"] == default_name  # constant unchanged
    assert set_body["is_overridden"] is True
    flagged = [s for s in set_body["strategies"] if s["is_live"]]
    assert len(flagged) == 1 and flagged[0]["name"] == target

    # The selection persists across requests (read back from the override file).
    assert client.get("/api/v1/strategies").json()["live_strategy"] == target

    # Reset reverts to the constant and clears the override flag.
    reset_body = client.post("/api/v1/strategies/live/reset").json()
    assert reset_body["live_strategy"] == default_name
    assert reset_body["is_overridden"] is False


def test_set_live_unknown_strategy_422(client: TestClient, isolated_override) -> None:
    resp = client.post("/api/v1/strategies/live", json={"name": "not_a_real_strategy"})
    assert resp.status_code == 422


@pytest.mark.parametrize(
    "contents",
    [
        "not json at all",          # invalid JSON -> ValueError
        "null",                     # valid JSON, not an object
        '"baseV1_roll20"',          # valid JSON string, not an object
        "[1, 2, 3]",                # valid JSON array, not an object
        '{"live_strategy": [1, 2]}',  # object, but value is an unhashable non-str
        '{"live_strategy": "nope"}',  # object, but name not in registry
    ],
)
def test_malformed_override_falls_back_to_default(
    client: TestClient, isolated_override, contents: str
) -> None:
    """A malformed override file must never crash the API/live run (it falls back)."""
    isolated_override.write_text(contents, encoding="utf-8")
    body = client.get("/api/v1/strategies").json()
    assert body["live_strategy"] == body["default_strategy"]
    assert body["is_overridden"] is False
