"""
Unified ICT Market Structure Engine.

Coordinates fractal swing detection, structural break identification (BOS / CHoCH),
Fair Value Gaps, Liquidity Sweeps, Market Structure Shifts, and Order Blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import pandas as pd

from src.ict.fvg import detect_displacements, detect_fair_value_gaps
from src.ict.liquidity import detect_liquidity_sweeps, detect_market_structure_shifts
from src.ict.models import (
    FairValueGap,
    FVGStatus,
    LiquiditySweep,
    MarketStructureShift,
    MarketTrend,
    OrderBlock,
    StructureBreak,
    SwingPoint,
)
from src.ict.order_blocks import detect_order_blocks
from src.ict.structure import detect_market_structure
from src.ict.swings import detect_swing_points


@dataclass
class ICTAnalysisResult:
    """
    Comprehensive outcome of ICT market structure analysis.
    """
    symbol: str
    timeframe: str
    total_bars: int
    current_trend: MarketTrend
    swings: List[SwingPoint] = field(default_factory=list)
    structure_breaks: List[StructureBreak] = field(default_factory=list)
    fvgs: List[FairValueGap] = field(default_factory=list)
    liquidity_sweeps: List[LiquiditySweep] = field(default_factory=list)
    market_structure_shifts: List[MarketStructureShift] = field(default_factory=list)
    order_blocks: List[OrderBlock] = field(default_factory=list)
    displacement_indices: List[int] = field(default_factory=list)

    @property
    def bos_count(self) -> int:
        return sum(1 for b in self.structure_breaks if b.break_type.value == "BOS")

    @property
    def choch_count(self) -> int:
        return sum(1 for b in self.structure_breaks if b.break_type.value == "CHoCH")

    @property
    def active_fvgs(self) -> List[FairValueGap]:
        return [f for f in self.fvgs if f.status != FVGStatus.FULLY_MITIGATED]

    @property
    def active_order_blocks(self) -> List[OrderBlock]:
        return [ob for ob in self.order_blocks if not ob.is_mitigated]

    def summary(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "total_bars": self.total_bars,
            "current_trend": self.current_trend.value,
            "total_swings": len(self.swings),
            "bos_count": self.bos_count,
            "choch_count": self.choch_count,
            "total_fvgs": len(self.fvgs),
            "active_fvgs": len(self.active_fvgs),
            "liquidity_sweeps": len(self.liquidity_sweeps),
            "market_structure_shifts": len(self.market_structure_shifts),
            "order_blocks": len(self.order_blocks),
            "active_order_blocks": len(self.active_order_blocks),
            "displacement_candles": len(self.displacement_indices),
        }


def analyze_market_structure(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
    swing_window: int = 2,
    break_on_close: bool = True,
    min_gap_points: float = 0.0,
    track_mitigation: bool = True,
    displacement_atr_period: int = 14,
    displacement_multiplier: float = 1.5,
    displacement_min_body_ratio: float = 0.6,
) -> ICTAnalysisResult:
    """
    Run the end-to-end ICT Market Structure Engine on a clean OHLCV dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV market dataframe with UTC timestamps.
    symbol : str
        Trading symbol name.
    timeframe : str
        Timeframe ('M5', 'M15', 'H1', 'H4').
    swing_window : int, default 2
        Fractal lookback/lookforward radius.
    break_on_close : bool, default True
        Require candle body close for BOS and CHoCH validation.
    min_gap_points : float, default 0.0
        Minimum price gap threshold for Fair Value Gaps.
    track_mitigation : bool, default True
        Forward mitigation analysis for FVGs and Order Blocks.

    Returns
    -------
    ICTAnalysisResult
        Structured technical result object containing all detected features.
    """
    if df.empty:
        return ICTAnalysisResult(
            symbol=symbol,
            timeframe=timeframe,
            total_bars=0,
            current_trend=MarketTrend.NEUTRAL,
        )

    # 1. Detect Fractal Swings
    swings = detect_swing_points(df, window=swing_window)

    # 2. Detect Market Structure (BOS / CHoCH)
    structure_breaks, final_trend = detect_market_structure(
        df, swings, break_on_close=break_on_close
    )

    # 3. Detect Fair Value Gaps
    fvgs = detect_fair_value_gaps(
        df, min_gap_points=min_gap_points, track_mitigation=track_mitigation
    )

    # 4. Detect displacement using only the ATR baseline available before each bar.
    displacement_indices = detect_displacements(
        df,
        atr_period=displacement_atr_period,
        multiplier=displacement_multiplier,
        min_body_ratio=displacement_min_body_ratio,
    )

    # 5. Detect Liquidity Sweeps & Market Structure Shifts
    sweeps = detect_liquidity_sweeps(df, swings)
    shifts = detect_market_structure_shifts(sweeps, structure_breaks, fvgs=fvgs)

    # 6. Detect Institutional Order Blocks
    order_blocks = detect_order_blocks(
        df, fvgs=fvgs, structure_breaks=structure_breaks, track_mitigation=track_mitigation
    )

    return ICTAnalysisResult(
        symbol=symbol,
        timeframe=timeframe,
        total_bars=len(df),
        current_trend=final_trend,
        swings=swings,
        structure_breaks=structure_breaks,
        fvgs=fvgs,
        liquidity_sweeps=sweeps,
        market_structure_shifts=shifts,
        order_blocks=order_blocks,
        displacement_indices=displacement_indices,
    )
