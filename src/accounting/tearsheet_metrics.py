
from dataclasses import dataclass
from typing import List

from accounting.metrics import DayMetrics

@dataclass(frozen=True)
class TearsheetMetrics:
    scenario_id: str
    start_date: str
    end_date: str
    cagr: float
    total_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    volatility: float
    # ... more fields

def compute_tearsheet(daily_metrics: List[DayMetrics], risk_free_rate=0.02) -> TearsheetMetrics:
    # Convert to returns series
    # Calculate metrics vectorized with pandas/numpy
    # Return dataclass
    pass

def load_scenario_metrics(scenario_id: str) -> List[DayMetrics]:
    # Query DB or load from JSON
    pass