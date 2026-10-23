"""Independent Smart Money Concepts (SMC) event models.

These models intentionally do not reuse ICT-specific FVG, displacement, MSS,
kill-zone, or Consequent Encroachment types. Timestamps represent when an
observation became knowable, not merely the candle on which a pivot formed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import pandas as pd


class SMCDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class SMCSwingType(str, Enum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"


class SMCStructureType(str, Enum):
    INITIAL_BREAK = "INITIAL_BREAK"
    BOS = "BOS"
    CHOCH = "CHoCH"


class SMCLiquidityType(str, Enum):
    BUY_SIDE = "BUY_SIDE"     # Liquidity above approximately equal highs.
    SELL_SIDE = "SELL_SIDE"   # Liquidity below approximately equal lows.


class SMCOrderBlockStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MITIGATED = "MITIGATED"
    INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class SMCSwingPoint:
    index: int
    time: pd.Timestamp
    price: float
    swing_type: SMCSwingType
    classification: str
    confirmed_index: int
    confirmed_time: pd.Timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "time": self.time.isoformat(),
            "price": self.price,
            "swing_type": self.swing_type.value,
            "classification": self.classification,
            "confirmed_index": self.confirmed_index,
            "confirmed_time": self.confirmed_time.isoformat(),
        }


@dataclass(frozen=True)
class SMCStructureBreak:
    break_type: SMCStructureType
    direction: SMCDirection
    broken_swing: SMCSwingPoint
    break_index: int
    break_time: pd.Timestamp
    break_price: float
    prior_trend: SMCDirection
    resulting_trend: SMCDirection

    def to_dict(self) -> Dict[str, Any]:
        return {
            "break_type": self.break_type.value,
            "direction": self.direction.value,
            "broken_swing_price": self.broken_swing.price,
            "broken_swing_time": self.broken_swing.time.isoformat(),
            "break_index": self.break_index,
            "break_time": self.break_time.isoformat(),
            "break_price": self.break_price,
            "prior_trend": self.prior_trend.value,
            "resulting_trend": self.resulting_trend.value,
        }


@dataclass(frozen=True)
class SMCLiquidityPool:
    liquidity_type: SMCLiquidityType
    level: float
    first_swing_index: int
    second_swing_index: int
    first_swing_time: pd.Timestamp
    second_swing_time: pd.Timestamp
    created_index: int
    created_time: pd.Timestamp
    tolerance: float

    @property
    def member_swing_indices(self) -> List[int]:
        return [self.first_swing_index, self.second_swing_index]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "liquidity_type": self.liquidity_type.value,
            "level": self.level,
            "first_swing_index": self.first_swing_index,
            "second_swing_index": self.second_swing_index,
            "first_swing_time": self.first_swing_time.isoformat(),
            "second_swing_time": self.second_swing_time.isoformat(),
            "created_index": self.created_index,
            "created_time": self.created_time.isoformat(),
            "tolerance": self.tolerance,
        }


@dataclass(frozen=True)
class SMCLiquiditySweep:
    liquidity_pool: SMCLiquidityPool
    sweep_index: int
    sweep_time: pd.Timestamp
    sweep_price: float
    close_price: float
    penetration: float

    @property
    def liquidity_type(self) -> SMCLiquidityType:
        return self.liquidity_pool.liquidity_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "liquidity_type": self.liquidity_type.value,
            "liquidity_level": self.liquidity_pool.level,
            "sweep_index": self.sweep_index,
            "sweep_time": self.sweep_time.isoformat(),
            "sweep_price": self.sweep_price,
            "close_price": self.close_price,
            "penetration": self.penetration,
        }


@dataclass
class SMCOrderBlock:
    direction: SMCDirection
    origin_index: int
    origin_time: pd.Timestamp
    high: float
    low: float
    open: float
    close: float
    created_index: int
    created_time: pd.Timestamp
    confirming_break_type: SMCStructureType
    status: SMCOrderBlockStatus = SMCOrderBlockStatus.ACTIVE
    mitigation_index: Optional[int] = None
    mitigation_time: Optional[pd.Timestamp] = None
    invalidation_index: Optional[int] = None
    invalidation_time: Optional[pd.Timestamp] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction.value,
            "origin_index": self.origin_index,
            "origin_time": self.origin_time.isoformat(),
            "high": self.high,
            "low": self.low,
            "open": self.open,
            "close": self.close,
            "created_index": self.created_index,
            "created_time": self.created_time.isoformat(),
            "confirming_break_type": self.confirming_break_type.value,
            "status": self.status.value,
            "mitigation_index": self.mitigation_index,
            "mitigation_time": self.mitigation_time.isoformat() if self.mitigation_time else None,
            "invalidation_index": self.invalidation_index,
            "invalidation_time": self.invalidation_time.isoformat() if self.invalidation_time else None,
        }


@dataclass
class SMCAnalysisResult:
    symbol: str
    timeframe: str
    total_bars: int
    current_trend: SMCDirection = SMCDirection.NEUTRAL
    swings: List[SMCSwingPoint] = field(default_factory=list)
    structure_breaks: List[SMCStructureBreak] = field(default_factory=list)
    liquidity_pools: List[SMCLiquidityPool] = field(default_factory=list)
    liquidity_sweeps: List[SMCLiquiditySweep] = field(default_factory=list)
    order_blocks: List[SMCOrderBlock] = field(default_factory=list)
    equilibrium: Optional[float] = None
    dealing_range_high: Optional[float] = None
    dealing_range_low: Optional[float] = None
    current_zone: str = "UNAVAILABLE"

    @property
    def bos_count(self) -> int:
        return sum(event.break_type == SMCStructureType.BOS for event in self.structure_breaks)

    @property
    def choch_count(self) -> int:
        return sum(event.break_type == SMCStructureType.CHOCH for event in self.structure_breaks)

    @property
    def initial_break_count(self) -> int:
        return sum(event.break_type == SMCStructureType.INITIAL_BREAK for event in self.structure_breaks)

    @property
    def active_order_blocks(self) -> List[SMCOrderBlock]:
        return [ob for ob in self.order_blocks if ob.status == SMCOrderBlockStatus.ACTIVE]

    def summary(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "total_bars": self.total_bars,
            "current_trend": self.current_trend.value,
            "total_swings": len(self.swings),
            "bos_count": self.bos_count,
            "choch_count": self.choch_count,
            "initial_break_count": self.initial_break_count,
            "liquidity_pools": len(self.liquidity_pools),
            "liquidity_sweeps": len(self.liquidity_sweeps),
            "order_blocks": len(self.order_blocks),
            "active_order_blocks": len(self.active_order_blocks),
            "equilibrium": self.equilibrium,
            "dealing_range_high": self.dealing_range_high,
            "dealing_range_low": self.dealing_range_low,
            "current_zone": self.current_zone,
        }
