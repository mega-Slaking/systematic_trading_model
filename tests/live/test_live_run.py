"""Live decision path: run_engine(LiveContext).

The external edges (price/macro fetch, DB persist, email, plotting) are mocked, so
this exercises the live wiring of the decision pipeline - the part that had drifted
out of sync with the backtest (returns view + volatility-surface hooks).
"""

import pandas as pd
import pytest

from src.context.live import LiveContext
from src.engine.run import run_engine

pytestmark = [pytest.mark.integration]


def _live_context(monkeypatch, etf_history, macro_history):
    ctx = LiveContext()
    # Deterministic synthetic inputs instead of live API calls.
    monkeypatch.setattr(ctx, "fetch_etf_prices", lambda: etf_history)
    monkeypatch.setattr(ctx, "fetch_macro_data", lambda: macro_history)
    # External side effects (sqlite write / email) are mocked; visualize is left as
    # the real (deprecated) no-op so the live flow exercises it.
    monkeypatch.setattr(ctx, "persist", lambda *a, **k: None)
    monkeypatch.setattr(ctx, "notify", lambda *a, **k: None)
    # Run "the day after" the last data point so all history is in the past.
    ctx.current_date = pd.Timestamp(etf_history["date"].max()) + pd.Timedelta(days=1)
    return ctx


def test_live_run_produces_valid_decision(
    synthetic_etf_history, synthetic_macro_history, monkeypatch
):
    ctx = _live_context(monkeypatch, synthetic_etf_history, synthetic_macro_history)

    decision = run_engine(ctx)

    assert decision is not None
    assert decision.regime is not None
    assert decision.final_weights is not None
    assert sum(decision.final_weights.values()) == pytest.approx(1.0)
    assert all(w >= 0.0 for w in decision.final_weights.values())


def test_live_run_records_traces(
    synthetic_etf_history, synthetic_macro_history, monkeypatch
):
    ctx = _live_context(monkeypatch, synthetic_etf_history, synthetic_macro_history)

    run_engine(ctx)

    assert len(ctx.decision_trace) == 1
    assert len(ctx.regime_trace) == 1
    assert ctx.decision_trace[0]["date"] == ctx.current_date


def test_live_run_builds_returns_view_when_absent(
    synthetic_etf_history, synthetic_macro_history, monkeypatch
):
    # LiveContext has no returns_view; run_engine must lazily build one (no AttributeError).
    ctx = _live_context(monkeypatch, synthetic_etf_history, synthetic_macro_history)
    assert not hasattr(ctx, "returns_view")

    decision = run_engine(ctx)
    assert decision is not None


def test_get_selected_price_today_returns_latest_close(synthetic_etf_history, monkeypatch):
    ctx = LiveContext()
    monkeypatch.setattr(ctx, "fetch_etf_prices", lambda: synthetic_etf_history)

    expected = float(
        synthetic_etf_history[synthetic_etf_history["ticker"] == "TLT"]
        .sort_values("date")["close"]
        .iloc[-1]
    )
    assert ctx.get_selected_price_today("TLT") == pytest.approx(expected)


def test_live_visualize_is_a_noop():
    # generate_daily_report is deprecated; visualize must do nothing and not raise.
    assert LiveContext().visualize("etf", "macro", "ps", "ms", "decision") is None


def test_live_run_invokes_persist_and_notify(
    synthetic_etf_history, synthetic_macro_history, monkeypatch
):
    ctx = LiveContext()
    monkeypatch.setattr(ctx, "fetch_etf_prices", lambda: synthetic_etf_history)
    monkeypatch.setattr(ctx, "fetch_macro_data", lambda: synthetic_macro_history)

    calls = {"persist": 0, "notify": 0}
    monkeypatch.setattr(ctx, "persist", lambda *a, **k: calls.__setitem__("persist", calls["persist"] + 1))
    monkeypatch.setattr(ctx, "notify", lambda *a, **k: calls.__setitem__("notify", calls["notify"] + 1))
    # visualize left as the real no-op -> the full live flow must complete.
    ctx.current_date = pd.Timestamp(synthetic_etf_history["date"].max()) + pd.Timedelta(days=1)

    decision = run_engine(ctx)

    assert decision is not None
    assert calls == {"persist": 1, "notify": 1}
