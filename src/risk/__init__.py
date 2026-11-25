"""Capital Preservation and Risk Management package for GoldFlow."""
from __future__ import annotations

from src.risk.engine import DailyDrawdownTracker, RiskConfig, RiskEngine
from src.risk.lot_sizing import LotSizingResult, calculate_xauusd_lot_size
from src.risk.trade_management import (
    adjust_candidate_with_atr,
    check_breakeven_trigger,
    compute_atr,
)

__all__ = [
    "RiskConfig",
    "DailyDrawdownTracker",
    "RiskEngine",
    "LotSizingResult",
    "calculate_xauusd_lot_size",
    "compute_atr",
    "adjust_candidate_with_atr",
    "check_breakeven_trigger",
]

