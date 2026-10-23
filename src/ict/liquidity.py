"""
Liquidity Sweeps & Market Structure Shift (MSS) Engine.

Identifies buy-side and sell-side liquidity sweeps (stop runs / false breakouts)
and detects high-confluence Market Structure Shifts (sweep + counter-displacement).
"""

from __future__ import annotations

from typing import List, Optional
import pandas as pd

from src.ict.models import (
    FairValueGap,
    LiquiditySweep,
    MarketStructureShift,
    MarketTrend,
    StructureBreak,
    SweepType,
    SwingPoint,
    SwingType,
)


def detect_liquidity_sweeps(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    min_wick_penetration: float = 0.0,
) -> List[LiquiditySweep]:
    """
    Detect buy-side (BSL) and sell-side (SSL) liquidity sweeps.

    A sweep occurs when price penetrates a confirmed swing level with its wick
    but closes back inside the range on the same candle.

    Parameters
    ----------
    df : pd.DataFrame
        OHLC market dataframe.
    swings : List[SwingPoint]
        Confirmed swing points.
    min_wick_penetration : float, default 0.0
        Minimum price distance penetrated beyond the swing point.

    Returns
    -------
    List[LiquiditySweep]
        Chronological list of detected liquidity sweeps.
    """
    if df.empty or not swings:
        return []

    sweeps: List[LiquiditySweep] = []
    n = len(df)
    times = df["time"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()

    # Track which swings have already been swept or broken to avoid infinite repeat triggers
    active_shs = [s for s in swings if s.swing_type == SwingType.SWING_HIGH]
    active_sls = [s for s in swings if s.swing_type == SwingType.SWING_LOW]

    for t in range(n):
        curr_high = highs[t]
        curr_low = lows[t]
        curr_close = closes[t]
        cand_time = pd.to_datetime(times[t], utc=True)

        # 1. Buy-Side Liquidity Sweeps (High > SwingHigh.price, Close <= SwingHigh.price)
        for sh in list(active_shs):
            # Only test after the swing was confirmed
            if t > sh.confirmed_index:
                if curr_high > sh.price:
                    penetration = float(curr_high - sh.price)
                    if curr_close <= sh.price and penetration >= min_wick_penetration:
                        sweep = LiquiditySweep(
                            sweep_type=SweepType.BUY_SIDE,
                            swept_swing=sh,
                            sweep_index=t,
                            sweep_time=cand_time,
                            sweep_price=float(curr_high),
                            close_price=float(curr_close),
                            wick_penetration=penetration,
                        )
                        sweeps.append(sweep)
                        active_shs.remove(sh)
                    elif curr_close > sh.price:
                        # Full body close break, no longer a candidate for a false-wick sweep
                        active_shs.remove(sh)

        # 2. Sell-Side Liquidity Sweeps (Low < SwingLow.price, Close >= SwingLow.price)
        for sl in list(active_sls):
            if t > sl.confirmed_index:
                if curr_low < sl.price:
                    penetration = float(sl.price - curr_low)
                    if curr_close >= sl.price and penetration >= min_wick_penetration:
                        sweep = LiquiditySweep(
                            sweep_type=SweepType.SELL_SIDE,
                            swept_swing=sl,
                            sweep_index=t,
                            sweep_time=cand_time,
                            sweep_price=float(curr_low),
                            close_price=float(curr_close),
                            wick_penetration=penetration,
                        )
                        sweeps.append(sweep)
                        active_sls.remove(sl)
                    elif curr_close < sl.price:
                        # Full body close break
                        active_sls.remove(sl)

    sweeps.sort(key=lambda s: s.sweep_index)
    return sweeps


def detect_market_structure_shifts(
    sweeps: List[LiquiditySweep],
    structure_breaks: List[StructureBreak],
    fvgs: Optional[List[FairValueGap]] = None,
    max_lag_bars: int = 10,
    require_fvg: bool = False,
) -> List[MarketStructureShift]:
    """
    Detect Market Structure Shifts (MSS).

    An MSS is identified when a liquidity sweep is promptly followed by
    a structural break in the opposite direction within `max_lag_bars`,
    reinforced optionally (or mandatory if require_fvg=True) by an FVG.

    Parameters
    ----------
    sweeps : List[LiquiditySweep]
        Detected liquidity sweeps.
    structure_breaks : List[StructureBreak]
        Detected BOS / CHoCH structural breaks.
    fvgs : List[FairValueGap], optional
        Detected Fair Value Gaps.
    max_lag_bars : int, default 10
        Maximum bar distance between sweep and structural break.
    require_fvg : bool, default False
        If True, only emits an MSS when a confirming FVG exists between sweep and break.

    Returns
    -------
    List[MarketStructureShift]
        Confirmed market structure shifts.
    """
    if not sweeps or not structure_breaks:
        return []

    shifts: List[MarketStructureShift] = []

    for sweep in sweeps:
        # Determine expected shift direction
        # Buy-Side sweep -> Expect Bearish shift
        # Sell-Side sweep -> Expect Bullish shift
        target_dir = MarketTrend.BEARISH if sweep.sweep_type == SweepType.BUY_SIDE else MarketTrend.BULLISH

        for s_break in structure_breaks:
            if s_break.direction == target_dir and sweep.sweep_index < s_break.break_index <= (sweep.sweep_index + max_lag_bars):
                # Check for associated FVG between sweep and break
                matched_fvg: Optional[FairValueGap] = None
                if fvgs:
                    for fvg in fvgs:
                        if sweep.sweep_index <= fvg.candle_index <= s_break.break_index:
                            if (target_dir == MarketTrend.BULLISH and fvg.gap_type.value == "BULLISH") or \
                               (target_dir == MarketTrend.BEARISH and fvg.gap_type.value == "BEARISH"):
                                matched_fvg = fvg
                                break

                if require_fvg and matched_fvg is None:
                    continue

                shift = MarketStructureShift(
                    sweep=sweep,
                    structure_break=s_break,
                    displacement_fvg=matched_fvg,
                    shift_index=s_break.break_index,
                    shift_time=s_break.break_time,
                    direction=target_dir,
                )
                shifts.append(shift)
                break

    return shifts
