"""Comprehensive Capital Preservation and Risk Engine for GoldFlow."""
from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import math
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from src.risk.lot_sizing import LotSizingResult, calculate_xauusd_lot_size
from src.strategy.smc_mtf import _as_utc_timestamp


# Rejection reason constants
REJECTED_MAX_CONCURRENCY = "REJECTED_MAX_CONCURRENCY"
REJECTED_SPREAD_TOO_HIGH = "REJECTED_SPREAD_TOO_HIGH"
REJECTED_DAILY_DRAWDOWN_LIMIT = "REJECTED_DAILY_DRAWDOWN_LIMIT"
REJECTED_INSUFFICIENT_EQUITY = "REJECTED_INSUFFICIENT_EQUITY"
REJECTED_INVALID_STOP_DISTANCE = "REJECTED_INVALID_STOP_DISTANCE"
REJECTED_STOP_TOO_WIDE_FOR_MIN_LOT = "REJECTED_STOP_TOO_WIDE_FOR_MIN_LOT"


@dataclass(frozen=True)
class RiskConfig:
    """Institutional capital preservation parameters."""
    account_equity: float = 10_000.0
    risk_per_trade_pct: float = 0.005  # 0.5% risk per trade
    max_daily_drawdown_pct: float = 0.02  # 2.0% daily circuit breaker
    max_concurrency: int = 1  # Strict single position
    max_spread_dollars: float = 0.35  # $0.35/oz maximum allowable spread
    contract_size_oz: float = 100.0  # 100 oz per standard lot
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lots: float = 100.0
    commission_per_lot_per_side: float = 0.0


class DailyDrawdownTracker:
    """Tracks daily realized and peak equity with automatic 00:00:00 UTC reset."""

    def __init__(self, initial_equity: float, max_daily_drawdown_pct: float) -> None:
        self.initial_equity = float(initial_equity)
        self.max_daily_drawdown_pct = float(max_daily_drawdown_pct)
        self.current_date: Optional[datetime.date] = None
        self.day_starting_equity: float = float(initial_equity)
        self.day_realized_pnl: float = 0.0
        self.circuit_breaker_active: bool = False

    def _sync_date(self, current_time: pd.Timestamp, current_equity: float) -> None:
        ts_utc = _as_utc_timestamp(current_time, label="drawdown tracking time")
        dt_date = ts_utc.date()
        if self.current_date != dt_date:
            # New calendar day (00:00:00 UTC reset)
            self.current_date = dt_date
            self.day_starting_equity = float(current_equity)
            self.day_realized_pnl = 0.0
            self.circuit_breaker_active = False

    def on_trade_closed(self, closed_time: pd.Timestamp, net_pnl: float, new_equity: float) -> None:
        """Record trade close and verify if daily drawdown limit was breached."""
        self._sync_date(closed_time, new_equity - net_pnl)
        self.day_realized_pnl += net_pnl
        max_allowable_loss = self.day_starting_equity * self.max_daily_drawdown_pct
        if self.day_realized_pnl <= -max_allowable_loss:
            self.circuit_breaker_active = True

    def is_circuit_breaker_active(self, current_time: pd.Timestamp, current_equity: float) -> bool:
        """Check if trading is currently halted for the remainder of the calendar day."""
        self._sync_date(current_time, current_equity)
        return self.circuit_breaker_active

    def get_status(self) -> dict[str, Any]:
        return {
            "current_date": self.current_date.isoformat() if self.current_date else None,
            "day_starting_equity": self.day_starting_equity,
            "day_realized_pnl": self.day_realized_pnl,
            "circuit_breaker_active": self.circuit_breaker_active,
            "daily_drawdown_limit_cash": self.day_starting_equity * self.max_daily_drawdown_pct,
        }


class RiskEngine:
    """Orchestrates sizing, position concurrency, spread thresholds, and daily loss protection."""

    def __init__(self, config: Optional[RiskConfig] = None) -> None:
        self.config = config or RiskConfig()
        self.tracker = DailyDrawdownTracker(
            initial_equity=self.config.account_equity,
            max_daily_drawdown_pct=self.config.max_daily_drawdown_pct,
        )

    def validate_candidate_entry(
        self,
        *,
        entry_time: pd.Timestamp,
        entry_price: float,
        stop_loss: float,
        spread_usd: float,
        active_positions_count: int,
        current_equity: float,
    ) -> Tuple[bool, Optional[float], Optional[str]]:
        """Validate candidate against all capital preservation rules.

        Returns:
            (is_approved, lot_size, rejection_reason)
        """
        # 1. Concurrency limit
        if active_positions_count >= self.config.max_concurrency:
            return False, None, REJECTED_MAX_CONCURRENCY

        # 2. Maximum allowable spread limit
        if spread_usd > self.config.max_spread_dollars:
            return False, None, REJECTED_SPREAD_TOO_HIGH

        # 3. Daily drawdown circuit breaker
        if self.tracker.is_circuit_breaker_active(entry_time, current_equity):
            return False, None, REJECTED_DAILY_DRAWDOWN_LIMIT

        # 4. Monetary lot sizing
        sizing = calculate_xauusd_lot_size(
            equity=current_equity,
            risk_pct=self.config.risk_per_trade_pct,
            entry_price=entry_price,
            stop_loss=stop_loss,
            contract_size_oz=self.config.contract_size_oz,
            min_lot=self.config.min_lot,
            lot_step=self.config.lot_step,
            max_lots=self.config.max_lots,
            commission_per_lot_per_side=self.config.commission_per_lot_per_side,
        )

        if not sizing.is_valid:
            return False, None, sizing.rejection_reason

        return True, sizing.lots, None

