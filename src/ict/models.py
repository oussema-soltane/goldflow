"""
Core data models and enumerations for ICT Market Structure Engine.

All events record both their formation timestamp and their confirmation timestamp
to strictly prevent look-ahead bias in downstream analysis and backtesting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import pandas as pd


class SwingType(str, Enum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"


class SwingClassification(str, Enum):
    HIGHER_HIGH = "HH"
    LOWER_HIGH = "LH"
    HIGHER_LOW = "HL"
    LOWER_LOW = "LL"
    INITIAL = "INIT"


class BreakType(str, Enum):
    BOS = "BOS"      # Break of Structure (trend continuation)
    CHOCH = "CHoCH"  # Change of Character (trend reversal)


class MarketTrend(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class FVGType(str, Enum):
    BULLISH = "BULLISH"  # Imbalance: Low[i+1] > High[i-1]
    BEARISH = "BEARISH"  # Imbalance: High[i+1] < Low[i-1]


class FVGStatus(str, Enum):
    UNTESTED = "UNTESTED"
    PARTIALLY_MITIGATED = "PARTIALLY_MITIGATED"
    FULLY_MITIGATED = "FULLY_MITIGATED"


class SweepType(str, Enum):
    BUY_SIDE = "BUY_SIDE"    # Wick broke above Swing High, but closed below
    SELL_SIDE = "SELL_SIDE"  # Wick broke below Swing Low, but closed above


class OrderBlockType(str, Enum):
    BULLISH = "BULLISH"  # Last down candle before strong upward impulse
    BEARISH = "BEARISH"  # Last up candle before strong downward impulse


@dataclass(frozen=True)
class SwingPoint:
    """
    A confirmed local price extremum (fractal swing point).
    
    Attributes
    ----------
    index : int
        Positional index where the extremum candle formed.
    time : pd.Timestamp
        UTC timestamp of the extremum candle.
    price : float
        Extremum price (High for swing high, Low for swing low).
    swing_type : SwingType
        SWING_HIGH or SWING_LOW.
    classification : SwingClassification
        HH, LH, HL, LL, or INIT relative to preceding confirmed swing of same type.
    confirmed_index : int
        Positional index when the swing became confirmed (index + window).
    confirmed_time : pd.Timestamp
        UTC timestamp of confirmation bar. Crucial for zero look-ahead bias!
    """
    index: int
    time: pd.Timestamp
    price: float
    swing_type: SwingType
    classification: SwingClassification
    confirmed_index: int
    confirmed_time: pd.Timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "time": self.time.isoformat() if hasattr(self.time, "isoformat") else str(self.time),
            "price": self.price,
            "swing_type": self.swing_type.value,
            "classification": self.classification.value,
            "confirmed_index": self.confirmed_index,
            "confirmed_time": self.confirmed_time.isoformat() if hasattr(self.confirmed_time, "isoformat") else str(self.confirmed_time),
        }


@dataclass(frozen=True)
class StructureBreak:
    """
    Break of Structure (BOS) or Change of Character (CHoCH).
    
    Attributes
    ----------
    break_type : BreakType
        BOS or CHOCH.
    direction : MarketTrend
        BULLISH (broke above swing high) or BEARISH (broke below swing low).
    broken_swing : SwingPoint
        The swing point that was breached.
    break_index : int
        Index of the candle that executed the structural break.
    break_time : pd.Timestamp
        UTC timestamp of the breaking candle.
    break_price : float
        Close price (or High/Low) of the breaking candle.
    prior_trend : MarketTrend
        Trend state immediately prior to this break.
    resulting_trend : MarketTrend
        New trend state after this break.
    """
    break_type: BreakType
    direction: MarketTrend
    broken_swing: SwingPoint
    break_index: int
    break_time: pd.Timestamp
    break_price: float
    prior_trend: MarketTrend
    resulting_trend: MarketTrend

    def to_dict(self) -> Dict[str, Any]:
        return {
            "break_type": self.break_type.value,
            "direction": self.direction.value,
            "broken_swing_price": self.broken_swing.price,
            "broken_swing_time": str(self.broken_swing.time),
            "break_index": self.break_index,
            "break_time": self.break_time.isoformat() if hasattr(self.break_time, "isoformat") else str(self.break_time),
            "break_price": self.break_price,
            "prior_trend": self.prior_trend.value,
            "resulting_trend": self.resulting_trend.value,
        }


@dataclass
class FairValueGap:
    """
    3-candle imbalance (Fair Value Gap).
    
    Attributes
    ----------
    gap_type : FVGType
        BULLISH or BEARISH.
    candle_index : int
        Index of middle displacement candle (i).
    creation_index : int
        Index when FVG is confirmed (i+1).
    creation_time : pd.Timestamp
        UTC timestamp when FVG is confirmed.
    top_price : float
        Upper price boundary of the gap.
    bottom_price : float
        Lower price boundary of the gap.
    consequent_encroachment : float
        50% midpoint of the gap (CE).
    size : float
        Height of the gap in price points.
    status : FVGStatus
        UNTESTED, PARTIALLY_MITIGATED, or FULLY_MITIGATED.
    mitigation_index : Optional[int]
        Index of first candle that entered or invalidated the FVG.
    mitigation_time : Optional[pd.Timestamp]
        UTC timestamp of mitigation.
    """
    gap_type: FVGType
    candle_index: int
    creation_index: int
    creation_time: pd.Timestamp
    top_price: float
    bottom_price: float
    consequent_encroachment: float
    size: float
    status: FVGStatus = FVGStatus.UNTESTED
    mitigation_index: Optional[int] = None
    mitigation_time: Optional[pd.Timestamp] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gap_type": self.gap_type.value,
            "candle_index": self.candle_index,
            "creation_index": self.creation_index,
            "creation_time": self.creation_time.isoformat() if hasattr(self.creation_time, "isoformat") else str(self.creation_time),
            "top_price": self.top_price,
            "bottom_price": self.bottom_price,
            "consequent_encroachment": self.consequent_encroachment,
            "size": self.size,
            "status": self.status.value,
            "mitigation_index": self.mitigation_index,
            "mitigation_time": self.mitigation_time.isoformat() if self.mitigation_time is not None else None,
        }


@dataclass(frozen=True)
class LiquiditySweep:
    """
    Purge of resting buy/sell liquidity above/below a confirmed swing point.
    
    A sweep occurs when price penetrates a confirmed swing level with its wick
    but closes back inside the range on the same candle (false breakout / stop run).
    """
    sweep_type: SweepType
    swept_swing: SwingPoint
    sweep_index: int
    sweep_time: pd.Timestamp
    sweep_price: float  # High for buy-side sweep, Low for sell-side sweep
    close_price: float  # Close price verifying rejection back inside range
    wick_penetration: float  # Price distance penetrated beyond swing level

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sweep_type": self.sweep_type.value,
            "swept_swing_price": self.swept_swing.price,
            "swept_swing_time": str(self.swept_swing.time),
            "sweep_index": self.sweep_index,
            "sweep_time": self.sweep_time.isoformat() if hasattr(self.sweep_time, "isoformat") else str(self.sweep_time),
            "sweep_price": self.sweep_price,
            "close_price": self.close_price,
            "wick_penetration": self.wick_penetration,
        }


@dataclass
class OrderBlock:
    """
    Institutional Order Block.
    
    The last opposing candle prior to a strong displacement that causes an FVG
    or breaks structure.
    """
    ob_type: OrderBlockType
    candle_index: int
    candle_time: pd.Timestamp
    high: float
    low: float
    open: float
    close: float
    volume: float
    confirmed_index: int = 0
    confirmed_time: Optional[pd.Timestamp] = None
    fvg_index: Optional[int] = None
    structure_break_index: Optional[int] = None
    is_mitigated: bool = False
    mitigation_index: Optional[int] = None
    mitigation_time: Optional[pd.Timestamp] = None
    is_invalidated: bool = False
    invalidation_index: Optional[int] = None
    invalidation_time: Optional[pd.Timestamp] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ob_type": self.ob_type.value,
            "candle_index": self.candle_index,
            "candle_time": self.candle_time.isoformat() if hasattr(self.candle_time, "isoformat") else str(self.candle_time),
            "confirmed_index": self.confirmed_index,
            "confirmed_time": self.confirmed_time.isoformat() if hasattr(self.confirmed_time, "isoformat") else str(self.confirmed_time),
            "high": self.high,
            "low": self.low,
            "open": self.open,
            "close": self.close,
            "volume": self.volume,
            "fvg_index": self.fvg_index,
            "structure_break_index": self.structure_break_index,
            "is_mitigated": self.is_mitigated,
            "mitigation_index": self.mitigation_index,
            "is_invalidated": self.is_invalidated,
            "invalidation_index": self.invalidation_index,
        }


@dataclass(frozen=True)
class MarketStructureShift:
    """
    Market Structure Shift (MSS):
    A liquidity sweep followed immediately by energetic counter-displacement
    that breaks a counter-swing with an FVG.
    """
    sweep: LiquiditySweep
    structure_break: StructureBreak
    displacement_fvg: Optional[FairValueGap]
    shift_index: int
    shift_time: pd.Timestamp
    direction: MarketTrend

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shift_index": self.shift_index,
            "shift_time": self.shift_time.isoformat() if hasattr(self.shift_time, "isoformat") else str(self.shift_time),
            "direction": self.direction.value,
            "sweep_price": self.sweep.sweep_price,
            "break_price": self.structure_break.break_price,
        }
