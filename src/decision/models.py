from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Decision:
    # --- metadata ---
    date: str
    rule_id: Optional[str] = None
    reason: Optional[str] = None

    # --- signals / state ---
    macro_state: Optional[dict] = None
    price_state: Optional[dict] = None
    regime: Optional[str] = None

    # --- directional intent ---
    direction: Optional[Dict[str, int]] = None  # e.g. {"TLT": 1, "AGG": 0, "SHY": -1}
    conviction: Optional[Dict[str, float]] = None

    # --- allocation stages ---
    base_weights: Optional[Dict[str, float]] = None
    sized_weights: Optional[Dict[str, float]] = None
    final_weights: Optional[Dict[str, float]] = None

    # --- risk / constraints ---
    gross_exposure: Optional[float] = None
    net_exposure: Optional[float] = None

    # --- portfolio context ---
    current_weights: Optional[Dict[str, float]] = None
    rebalance_deltas: Optional[Dict[str, float]] = None

    # --- execution ---
    trades: Optional[List] = None  # replace with Trade type later

    # --- audit/debug ---
    notes: List[str] = field(default_factory=list)