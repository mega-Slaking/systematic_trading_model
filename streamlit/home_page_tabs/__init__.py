"""Home page tabs module for scenario testing dashboard."""

from .nav_comparison import render_nav_comparison_tab
from .returns_analysis import render_returns_analysis_tab
from .tearsheet import render_tearsheet_tab
from .etf_prices import render_etf_prices_tab
from .volatility_features import render_volatility_features_tab

__all__ = [
    "render_nav_comparison_tab",
    "render_returns_analysis_tab",
    "render_tearsheet_tab",
    "render_etf_prices_tab",
    "render_volatility_features_tab",
]
