"""Tests for price normalization (src/engine/normalize.py)."""

import pandas as pd
import pytest

from src.engine.normalize import PriceNormalizer

pytestmark = pytest.mark.unit


def test_returns_last_valid_close_per_ticker():
    df = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02", "2020-01-01", "2020-01-02"],
            "ticker": ["TLT", "TLT", "AGG", "AGG"],
            "close": [100.0, 101.0, 50.0, 51.0],
        }
    )
    prices = PriceNormalizer.normalize_prices(df)
    assert prices == {"TLT": 101.0, "AGG": 51.0}


def test_uses_last_by_date_not_by_row_order():
    df = pd.DataFrame(
        {
            "date": ["2020-01-03", "2020-01-01", "2020-01-02"],
            "ticker": ["TLT", "TLT", "TLT"],
            "close": [103.0, 101.0, 102.0],
        }
    )
    # Rows are out of order; the latest *date* (Jan 3) should win.
    assert PriceNormalizer.normalize_prices(df) == {"TLT": 103.0}


def test_ignores_trailing_nan_and_takes_last_valid():
    df = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02", "2020-01-03"],
            "ticker": ["TLT", "TLT", "TLT"],
            "close": [100.0, 101.0, float("nan")],
        }
    )
    assert PriceNormalizer.normalize_prices(df) == {"TLT": 101.0}


def test_returns_none_when_a_ticker_has_no_valid_close():
    df = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-01"],
            "ticker": ["TLT", "AGG"],
            "close": [100.0, float("nan")],
        }
    )
    assert PriceNormalizer.normalize_prices(df) is None
