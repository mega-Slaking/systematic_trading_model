from dataclasses import dataclass, field
from typing import Dict, List, Literal
import pandas as pd


VolatilityMethod = Literal["rolling_std", "ewma", "garch"]


@dataclass
class VolatilityConfig:
    method: VolatilityMethod = "rolling_std"
    lookback_days: int = 20
    annualization_factor: int = 252
    min_history: int = 20
    ewma_lambda: float = 0.94
    garch_p: int = 1
    garch_q: int = 1
    garch_mean: str = "zero"
    garch_dist: str = "normal"
    garch_rescale_returns: bool = True
    garch_lookback_days: int = 756


@dataclass
class VolatilityRequest:
    etf_history: pd.DataFrame
    as_of_date: pd.Timestamp
    tickers: List[str]


@dataclass
class VolatilityEstimate:
    method: VolatilityMethod
    as_of_date: pd.Timestamp
    annualized: bool
    vols: Dict[str, float]
    notes: List[str] = field(default_factory=list)
    invalid_tickers: List[str] = field(default_factory=list)