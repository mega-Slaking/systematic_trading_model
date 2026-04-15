from dataclasses import dataclass, field
from typing import List, Literal
import pandas as pd


CovarianceMethod = Literal["sample_cov", "ewma_cov"]


@dataclass
class CovarianceConfig:
    method: CovarianceMethod = "sample_cov"
    lookback_days: int = 20
    annualization_factor: int = 252
    min_history: int = 20
    ewma_lambda: float = 0.94
    ewma_lookback_days: int = 756


@dataclass
class CovarianceRequest:
    etf_history: pd.DataFrame
    as_of_date: pd.Timestamp
    tickers: List[str]


@dataclass
class CovarianceEstimate:
    method: CovarianceMethod
    as_of_date: pd.Timestamp
    annualized: bool
    tickers: List[str]
    covariance_matrix: pd.DataFrame
    notes: List[str] = field(default_factory=list)
    invalid_tickers: List[str] = field(default_factory=list)