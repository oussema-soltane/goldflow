"""Monetary-risk-based lot sizing for XAU/USD."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional


@dataclass(frozen=True)
class LotSizingResult:
    """Result of monetary risk lot sizing calculation."""
    lots: float
    unrounded_lots: float
    risk_usd: float
    risk_distance: float
    dollar_risk_per_lot: float
    actual_risk_usd: float
    is_valid: bool
    rejection_reason: Optional[str] = None


def calculate_xauusd_lot_size(
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
    *,
    contract_size_oz: float = 100.0,
    min_lot: float = 0.01,
    lot_step: float = 0.01,
    max_lots: float = 100.0,
    commission_per_lot_per_side: float = 0.0,
) -> LotSizingResult:
    """Calculate exact position lot size for XAU/USD given monetary risk.

    Formula:
        risk_budget = equity * risk_pct
        risk_distance = abs(entry_price - stop_loss)
        dollar_risk_per_lot = risk_distance * contract_size_oz + 2 * commission_per_lot_per_side
        unrounded_lots = min(max_lots, risk_budget / dollar_risk_per_lot)
        lots = floor(unrounded_lots / lot_step) * lot_step

    Rounds strictly downward to prevent exceeding the risk budget.
    Rejects setups where min_lot exceeds the allowable risk budget.
    """
    if equity <= 0:
        return LotSizingResult(
            lots=0.0,
            unrounded_lots=0.0,
            risk_usd=0.0,
            risk_distance=0.0,
            dollar_risk_per_lot=0.0,
            actual_risk_usd=0.0,
            is_valid=False,
            rejection_reason="REJECTED_INSUFFICIENT_EQUITY",
        )

    if not 0 < risk_pct <= 1.0:
        return LotSizingResult(
            lots=0.0,
            unrounded_lots=0.0,
            risk_usd=0.0,
            risk_distance=0.0,
            dollar_risk_per_lot=0.0,
            actual_risk_usd=0.0,
            is_valid=False,
            rejection_reason="REJECTED_INVALID_RISK_PERCENTAGE",
        )

    risk_distance = abs(entry_price - stop_loss)
    if not math.isfinite(risk_distance) or risk_distance <= 1e-4:
        return LotSizingResult(
            lots=0.0,
            unrounded_lots=0.0,
            risk_usd=0.0,
            risk_distance=risk_distance,
            dollar_risk_per_lot=0.0,
            actual_risk_usd=0.0,
            is_valid=False,
            rejection_reason="REJECTED_INVALID_STOP_DISTANCE",
        )

    risk_budget = equity * risk_pct
    dollar_risk_per_lot = risk_distance * contract_size_oz + 2.0 * commission_per_lot_per_side

    unrounded_lots = min(max_lots, risk_budget / dollar_risk_per_lot)
    # Floor strictly to nearest lot_step
    lots = math.floor((unrounded_lots + 1e-12) / lot_step) * lot_step
    lots = round(lots, 8)

    if lots < min_lot:
        return LotSizingResult(
            lots=0.0,
            unrounded_lots=unrounded_lots,
            risk_usd=risk_budget,
            risk_distance=risk_distance,
            dollar_risk_per_lot=dollar_risk_per_lot,
            actual_risk_usd=0.0,
            is_valid=False,
            rejection_reason="REJECTED_STOP_TOO_WIDE_FOR_MIN_LOT",
        )

    actual_risk = lots * dollar_risk_per_lot

    return LotSizingResult(
        lots=lots,
        unrounded_lots=unrounded_lots,
        risk_usd=risk_budget,
        risk_distance=risk_distance,
        dollar_risk_per_lot=dollar_risk_per_lot,
        actual_risk_usd=actual_risk,
        is_valid=True,
        rejection_reason=None,
    )

