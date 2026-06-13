"""Tests for the Returns Analysis diagnostic service + endpoint.

The pure transforms (label/metadata parsing, primary holding, enrichment,
filtering, worst/best/dispersion tables, hover text) are DB-independent and
exercised directly; the endpoint shape test runs against the populated repo DB.
"""

from __future__ import annotations

import json
import re

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.services import returns_diagnostics as rd

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --------------------------------------------------------------------------- #
# Scenario label formatting
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("scenario_id", "expected"),
    [
        ("default", "Default"),
        ("baseV1_roll20", "Base / Roll 20"),
        ("baseV1_roll20_covlb20_tv03", "Base / Cov LB 20 / TV 3%"),
        ("baseV1_roll20_ewmacov_lam94_tv05", "Base / EWMA λ94 / TV 5%"),
        ("legacyBase_roll20_ewmacov_lam97_tv04", "Legacy / EWMA λ97 / TV 4%"),
    ],
)
def test_format_scenario_label_examples(scenario_id: str, expected: str) -> None:
    assert rd.format_scenario_label(scenario_id) == expected


def test_format_scenario_label_disambiguates_unknown_tokens() -> None:
    # The p00x penalty variants must not collapse to the same legend label.
    labels = {rd.format_scenario_label(s) for s in ("baseV1_roll20_p000", "baseV1_roll20_p005")}
    assert len(labels) == 2


def test_format_scenario_label_falls_back_safely() -> None:
    # Unknown family + unrecognised tokens are preserved (no collisions, no loss).
    assert rd.format_scenario_label("totally_custom_thing") == "totally / custom / thing"
    # Malformed / empty inputs never raise and never lose information.
    assert rd.format_scenario_label("") == ""
    assert rd.format_scenario_label("weird") == "weird"


# --------------------------------------------------------------------------- #
# Metadata parsing
# --------------------------------------------------------------------------- #
def test_parse_scenario_metadata_full() -> None:
    meta = rd.parse_scenario_metadata("baseV1_roll20_ewmacov_lam94_tv03")
    assert meta == {
        "family": "baseV1",
        "lookback": 20,
        "vol_method": "ewmacov",
        "cov_lookback": None,
        "ewma_lambda": 0.94,
        "target_vol": 0.03,
    }


def test_parse_scenario_metadata_covlb() -> None:
    meta = rd.parse_scenario_metadata("baseV1_roll20_covlb20_tv05")
    assert meta["vol_method"] == "covlb"
    assert meta["cov_lookback"] == 20
    assert meta["target_vol"] == 0.05
    assert meta["ewma_lambda"] is None


def test_parse_scenario_metadata_partial_and_malformed_do_not_raise() -> None:
    assert rd.parse_scenario_metadata("default")["family"] == "default"
    bad = rd.parse_scenario_metadata("")
    assert all(v is None for v in bad.values())


# --------------------------------------------------------------------------- #
# Primary holding
# --------------------------------------------------------------------------- #
def test_determine_primary_holding() -> None:
    assert rd.determine_primary_holding({"TLT": 0.4, "AGG": 0.55, "SHY": 0.05}) == "AGG"
    assert rd.determine_primary_holding({"TLT": 0.0, "AGG": 0.0}) == "Cash"
    assert rd.determine_primary_holding({}) is None
    assert rd.determine_primary_holding(None) is None
    # Long/short safe: largest absolute weight wins.
    assert rd.determine_primary_holding({"TLT": -0.8, "AGG": 0.3}) == "TLT"


# --------------------------------------------------------------------------- #
# Default selection
# --------------------------------------------------------------------------- #
def test_default_scenario_selection_prefers_representatives_and_caps() -> None:
    available = [
        "default",
        "baseV1_roll20",
        "baseV1_roll20_covlb20_tv03",
        "baseV1_roll20_ewmacov_lam94_tv03",
        "legacyBase_roll20_ewmacov_lam94_tv03",
        "baseV1_roll20_p000",
    ]
    chosen = rd.default_scenario_selection(available)  # default limit
    assert chosen[0] == "default"
    assert 3 <= len(chosen) <= 5
    assert all(s in available for s in chosen)
    # The page asks for 3 visible by default.
    three = rd.default_scenario_selection(available, limit=3)
    assert len(three) == 3
    assert three[0] == "default"


def test_default_scenario_selection_pads_thin_db() -> None:
    chosen = rd.default_scenario_selection(["weird_a", "weird_b", "weird_c", "weird_d"])
    assert 3 <= len(chosen) <= 5
    assert rd.default_scenario_selection(["only_one"], limit=3) == ["only_one"]


# --------------------------------------------------------------------------- #
# Diagnostic frame enrichment (left joins, weight parsing)
# --------------------------------------------------------------------------- #
def _results_frame() -> pd.DataFrame:
    rows = [
        ("2020-03-18", "baseV1_roll20", 1.10, -0.05, 0.0, 0.0,
         '{"TLT": 1.0, "AGG": 0.0, "SHY": 0.0}', "TLT", 1.0),
        ("2020-03-19", "baseV1_roll20", 1.05, 0.02, 0.1, 0.001,
         '{"TLT": 0.5, "AGG": 0.5, "SHY": 0.0}', "TLT", 0.5),
        ("2020-03-18", "default", 1.20, 0.01, 0.0, 0.0,
         '{"TLT": 0.2, "AGG": 0.6, "SHY": 0.2}', "AGG", 0.6),
    ]
    return pd.DataFrame(
        [
            {
                "date": d, "scenario_id": s, "nav": n, "ret": r,
                "turnover": tn, "total_cost": c, "weights": w,
                "top_asset": ta, "top_weight": tw,
            }
            for d, s, n, r, tn, c, w, ta, tw in rows
        ]
    ).assign(date=lambda df: pd.to_datetime(df["date"]))


def _regime_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-03-18", "2020-03-18"]),
            "scenario_id": ["baseV1_roll20", "default"],
            "inflation_regime": ["DIS", "DIS"],
            "growth_regime": ["BAD", "OK"],
            "labour_regime": ["WEAK", "WEAK"],
            "curve_state": ["INV", "NORM"],
            "macro_supports_duration": ["1", "0"],
        }
    )


def test_build_frame_parses_weights_and_left_joins_regime() -> None:
    diag = rd.build_returns_diagnostic_frame(_results_frame(), _regime_frame())
    assert len(diag) == 3  # left join never drops a return row
    row = diag[(diag["scenario_id"] == "baseV1_roll20") & (diag["date"] == "2020-03-18")].iloc[0]
    assert row["tlt_weight"] == 1.0
    assert row["primary_holding"] == "TLT"
    assert row["growth_regime"] == "BAD"
    # The 2020-03-19 row has no regime match -> nulls, not a dropped row.
    unmatched = diag[diag["date"] == "2020-03-19"].iloc[0]
    assert pd.isna(unmatched["growth_regime"])
    assert "daily_return" in diag.columns and "ret" not in diag.columns


def test_build_frame_handles_missing_regime_and_empty_input() -> None:
    diag = rd.build_returns_diagnostic_frame(_results_frame(), None)
    assert len(diag) == 3
    assert diag["growth_regime"].isna().all()
    assert rd.build_returns_diagnostic_frame(pd.DataFrame(), None).empty


# --------------------------------------------------------------------------- #
# Return-filter modes
# --------------------------------------------------------------------------- #
def _diag_for_filtering() -> pd.DataFrame:
    # 50 rows for one scenario: returns -0.025 .. +0.024 in 0.001 steps.
    vals = [(-25 + i) / 1000 for i in range(50)]
    return pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=50, freq="D"),
            "scenario_id": ["S"] * 50,
            "daily_return": vals,
        }
    )


def test_filter_all_passthrough() -> None:
    df = _diag_for_filtering()
    out = rd.filter_returns_for_view(df, ["S"], None, None, "all")
    assert len(out) == 50


def test_filter_abs_thresholds() -> None:
    df = _diag_for_filtering()
    out1 = rd.filter_returns_for_view(df, ["S"], None, None, "abs_gt_1pct")
    assert (out1["daily_return"].abs() > 0.01).all()
    out2 = rd.filter_returns_for_view(df, ["S"], None, None, "abs_gt_2pct")
    assert (out2["daily_return"].abs() > 0.02).all()
    assert len(out2) < len(out1)


def test_filter_worst_and_best_percentile_per_scenario() -> None:
    df = _diag_for_filtering()
    worst = rd.filter_returns_for_view(df, ["S"], None, None, "worst_1pct")
    best = rd.filter_returns_for_view(df, ["S"], None, None, "best_1pct")
    assert worst["daily_return"].max() <= df["daily_return"].quantile(0.01)
    assert best["daily_return"].min() >= df["daily_return"].quantile(0.99)


def test_filter_extremes_20_handles_small_scenarios() -> None:
    df = _diag_for_filtering()
    out = rd.filter_returns_for_view(df, ["S"], None, None, "extremes_20")
    assert len(out) == 40  # 20 highest + 20 lowest, no overlap at 50 rows
    small = df.head(10)
    out_small = rd.filter_returns_for_view(small, ["S"], None, None, "extremes_20")
    assert len(out_small) == 10  # fewer than 40 obs -> all kept, no error


def test_filter_date_range_and_empty() -> None:
    df = _diag_for_filtering()
    out = rd.filter_returns_for_view(
        df, ["S"], pd.Timestamp("2020-01-10"), pd.Timestamp("2020-01-20"), "all"
    )
    assert out["date"].min() >= pd.Timestamp("2020-01-10")
    assert out["date"].max() <= pd.Timestamp("2020-01-20")
    assert rd.filter_returns_for_view(pd.DataFrame(), ["S"], None, None, "all").empty


# --------------------------------------------------------------------------- #
# Dispersion + worst/best tables
# --------------------------------------------------------------------------- #
def test_dispersion_excludes_single_scenario_dates_and_picks_extremes() -> None:
    diag = rd.build_returns_diagnostic_frame(_results_frame(), _regime_frame())
    disp = rd.build_scenario_dispersion_table(diag)
    # Only 2020-03-18 has two scenarios; 2020-03-19 (one scenario) is excluded.
    # (Dates stay as Timestamps here; ISO normalization happens at df_to_table.)
    assert list(disp["date"]) == [pd.Timestamp("2020-03-18")]
    row = disp.iloc[0]
    assert row["dispersion"] == pytest.approx(0.01 - (-0.05))
    assert row["best_scenario_id"] == "default"  # +0.01
    assert row["worst_scenario_id"] == "baseV1_roll20"  # -0.05
    assert row["scenario_count"] == 2


def test_worst_best_tables_sort_and_limit() -> None:
    diag = rd.build_returns_diagnostic_frame(_results_frame(), _regime_frame())
    worst = rd.build_worst_returns_table(diag, limit=2)
    best = rd.build_best_returns_table(diag, limit=2)
    assert worst["daily_return"].is_monotonic_increasing
    assert best["daily_return"].is_monotonic_decreasing
    assert worst.iloc[0]["daily_return"] == pytest.approx(-0.05)
    # macro_supports_duration is mapped to Yes/No for display.
    assert set(worst["macro_supports_duration"].dropna()) <= {"Yes", "No"}


def test_tables_on_empty_frame_are_empty_not_errors() -> None:
    empty = rd.build_returns_diagnostic_frame(pd.DataFrame(), None)
    assert rd.build_worst_returns_table(empty).empty
    assert rd.build_scenario_dispersion_table(empty).empty


# --------------------------------------------------------------------------- #
# Hover text
# --------------------------------------------------------------------------- #
def test_hover_text_omits_missing_fields_and_never_shows_none() -> None:
    diag = rd.build_returns_diagnostic_frame(_results_frame(), _regime_frame())
    matched = diag[diag["date"] == "2020-03-18"].iloc[0]
    text = rd.build_hover_text(matched)
    assert "Growth regime:" in text and "Macro supports duration:" in text
    assert "None" not in text and "NaN" not in text and "null" not in text

    unmatched = diag[diag["date"] == "2020-03-19"].iloc[0]
    text2 = rd.build_hover_text(unmatched)
    assert "Growth regime:" not in text2  # missing field omitted entirely
    assert "None" not in text2 and "NaN" not in text2


# --------------------------------------------------------------------------- #
# Endpoint (against the populated repo DB)
# --------------------------------------------------------------------------- #
def test_returns_diagnostic_default_shape(client: TestClient) -> None:
    body = client.get("/api/v1/backtest-results/returns-diagnostic").json()
    all_scenarios = {m["scenario_id"] for m in body["available_scenarios"]}
    assert all_scenarios, "should list every scenario for the filters"

    # Fetch-all: series cover the whole grid; default_visible is the small subset.
    assert {s["scenario_id"] for s in body["series"]} == all_scenarios
    assert 1 <= len(body["default_visible"]) <= 3
    assert set(body["default_visible"]) <= all_scenarios

    assert _ISO_DATE.match(body["date_min"]) and _ISO_DATE.match(body["date_max"])
    for s in body["series"]:
        assert len(s["dates"]) == len(s["returns"])  # lean columnar pair (no hover)
        assert "hover" not in s
    for key in ("worst", "best", "dispersion"):
        assert "columns" in body[key] and "rows" in body[key]


def test_returns_diagnostic_point_drilldown(client: TestClient) -> None:
    # Pull a real (scenario, date) from the worst-returns table and drill into it.
    body = client.get("/api/v1/backtest-results/returns-diagnostic").json()
    worst = body["worst"]["rows"][0]
    detail = client.get(
        "/api/v1/backtest-results/returns-diagnostic/point",
        params={"scenario_id": worst["scenario_id"], "date": worst["date"]},
    ).json()
    assert detail["scenario_id"] == worst["scenario_id"]
    assert detail["date"] == worst["date"]
    assert detail["lines"], "should carry the formatted diagnostic lines"
    assert all("None" not in line and "NaN" not in line for line in detail["lines"])


def test_returns_diagnostic_point_unknown_is_404(client: TestClient) -> None:
    resp = client.get(
        "/api/v1/backtest-results/returns-diagnostic/point",
        params={"scenario_id": "nope", "date": "2020-01-01"},
    )
    assert resp.status_code == 404


def test_returns_diagnostic_filter_mode_shrinks_scatter_not_distribution(client: TestClient) -> None:
    sid = client.get("/api/v1/scenarios").json()["scenarios"][0]
    allp = client.get(
        "/api/v1/backtest-results/returns-diagnostic",
        params={"scenario_ids": sid, "filter_mode": "all"},
    ).json()
    out = client.get(
        "/api/v1/backtest-results/returns-diagnostic",
        params={"scenario_ids": sid, "filter_mode": "abs_gt_2pct"},
    ).json()
    all_pts = len(allp["series"][0]["dates"])
    out_pts = len(out["series"][0]["dates"]) if out["series"] else 0
    assert out_pts <= all_pts
    # Distribution (boxplot input) is unaffected by the chart's return filter.
    assert len(out["distribution"][0]["returns"]) == len(allp["distribution"][0]["returns"])


def test_returns_diagnostic_emits_strict_json(client: TestClient) -> None:
    text = client.get("/api/v1/backtest-results/returns-diagnostic").text
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text)
