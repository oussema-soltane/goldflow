"""Independent Smart Money Concepts (SMC) event models.

These models intentionally do not reuse ICT-specific FVG, displacement, MSS,
kill-zone, or Consequent Encroachment types. Timestamps represent when an
observation became knowable, not merely the candle on which a pivot formed.

SMC Fair Value Gaps (FVGs) differ from ICT FVGs: they do not require a
displacement candle condition. An SMC FVG is purely a 3-candle price imbalance
where candle i+1's body does not overlap the range spanned by candles i and
i+2 — i.e. gap(high[i], low[i+2]) > 0 for bullish, gap(high[i+2], low[i]) > 0
for bearish. The gap becomes knowable only after candle i+2 closes.
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


class SMCFVGType(str, Enum):
    BULLISH = "BULLISH"   # Bullish imbalance: gap between low[i+2] and high[i].
    BEARISH = "BEARISH"   # Bearish imbalance: gap between low[i] and high[i+2].


class SMCOrderBlockStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MITIGATED = "MITIGATED"
    INVALIDATED = "INVALIDATED"


class SMCFVGStatus(str, Enum):
    OPEN = "OPEN"         # No candle has yet closed inside the imbalance zone.
    PARTIAL = "PARTIAL"   # At least one candle closed inside the zone; zone not fully covered.
    CLOSED = "CLOSED"     # The zone has been fully covered by price action (CE or beyond).


class SMCBreakerBlockType(str, Enum):
    BULLISH = "BULLISH"   # Inverted from an invalidated Bearish OB; acts as support / demand
    BEARISH = "BEARISH"   # Inverted from an invalidated Bullish OB; acts as resistance / supply


class SMCBreakerBlockStatus(str, Enum):
    ACTIVE = "ACTIVE"           # Inverted, awaiting retest
    TESTED = "TESTED"           # Retested/mitigated by price overlap
    INVALIDATED = "INVALIDATED" # Price closed beyond the opposite boundary


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
class SMCFairValueGap:
    """A 3-candle price imbalance in the SMC framework.

    Confirmed at the close of candle ``creation_index`` (the third candle).
    No displacement or structural condition is required — this is a pure
    price-gap detection. The gap must be positive (i.e. the two outer candles'
    wicks do not overlap).

    Bullish FVG: low[i+2] > high[i]  → upside gap between candles i and i+2.
    Bearish FVG: high[i+2] < low[i]  → downside gap between candles i and i+2.

    ``top`` and ``bottom`` bound the imbalance zone. ``midpoint`` is the 50%
    Consequent Encroachment (CE) level. Status is updated by the engine.
    """
    fvg_type: SMCFVGType
    # origin_index = i (first candle of the 3-candle pattern).
    origin_index: int
    origin_time: pd.Timestamp
    # creation_index = i + 2 (third candle; when the gap became knowable).
    creation_index: int
    creation_time: pd.Timestamp
    top: float            # Upper boundary of the imbalance zone.
    bottom: float         # Lower boundary of the imbalance zone.
    midpoint: float       # 50% Consequent Encroachment (CE) level.
    size: float           # top - bottom.
    status: SMCFVGStatus = SMCFVGStatus.OPEN
    # First candle that closed inside the zone (partial fill / first touch).
    first_touch_index: Optional[int] = None
    first_touch_time: Optional[pd.Timestamp] = None
    # First candle whose close reached or crossed the midpoint (CE level).
    ce_index: Optional[int] = None
    ce_time: Optional[pd.Timestamp] = None
    # First candle whose close fully covered the zone (status → CLOSED).
    closed_index: Optional[int] = None
    closed_time: Optional[pd.Timestamp] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fvg_type": self.fvg_type.value,
            "origin_index": self.origin_index,
            "origin_time": self.origin_time.isoformat(),
            "creation_index": self.creation_index,
            "creation_time": self.creation_time.isoformat(),
            "top": self.top,
            "bottom": self.bottom,
            "midpoint": self.midpoint,
            "size": self.size,
            "status": self.status.value,
            "first_touch_index": self.first_touch_index,
            "first_touch_time": self.first_touch_time.isoformat() if self.first_touch_time else None,
            "ce_index": self.ce_index,
            "ce_time": self.ce_time.isoformat() if self.ce_time else None,
            "closed_index": self.closed_index,
            "closed_time": self.closed_time.isoformat() if self.closed_time else None,
        }


@dataclass
class SMCBreakerBlock:
    """An inverted Order Block in the SMC framework.

    When a Bullish Order Block's demand fails (price closes below its low),
    it inverts into a Bearish Breaker Block (resistance).
    When a Bearish Order Block's supply fails (price closes above its high),
    it inverts into a Bullish Breaker Block (support).

    ``created_index`` and ``created_time`` correspond to the invalidation bar
    of the original order block (the exact candle where the close breached the zone).
    """
    breaker_type: SMCBreakerBlockType
    source_order_block: SMCOrderBlock
    high: float
    low: float
    created_index: int
    created_time: pd.Timestamp
    status: SMCBreakerBlockStatus = SMCBreakerBlockStatus.ACTIVE
    retest_index: Optional[int] = None
    retest_time: Optional[pd.Timestamp] = None
    invalidation_index: Optional[int] = None
    invalidation_time: Optional[pd.Timestamp] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "breaker_type": self.breaker_type.value,
            "source_ob_origin_index": self.source_order_block.origin_index,
            "source_ob_direction": self.source_order_block.direction.value,
            "high": self.high,
            "low": self.low,
            "created_index": self.created_index,
            "created_time": self.created_time.isoformat(),
            "status": self.status.value,
            "retest_index": self.retest_index,
            "retest_time": self.retest_time.isoformat() if self.retest_time else None,
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
    breaker_blocks: List[SMCBreakerBlock] = field(default_factory=list)
    fair_value_gaps: List[SMCFairValueGap] = field(default_factory=list)
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

    @property
    def active_breaker_blocks(self) -> List[SMCBreakerBlock]:
        return [bb for bb in self.breaker_blocks if bb.status == SMCBreakerBlockStatus.ACTIVE]

    @property
    def active_fair_value_gaps(self) -> List[SMCFairValueGap]:
        """FVGs that are OPEN or PARTIAL (have not yet been fully closed)."""
        return [fvg for fvg in self.fair_value_gaps if fvg.status != SMCFVGStatus.CLOSED]

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
            "breaker_blocks": len(self.breaker_blocks),
            "active_breaker_blocks": len(self.active_breaker_blocks),
            "fair_value_gaps": len(self.fair_value_gaps),
            "active_fair_value_gaps": len(self.active_fair_value_gaps),
            "equilibrium": self.equilibrium,
            "dealing_range_high": self.dealing_range_high,
            "dealing_range_low": self.dealing_range_low,
            "current_zone": self.current_zone,
        }
