"""
Market Structure Engine: Break of Structure (BOS) & Change of Character (CHoCH).

Evaluates structural breaks forward in time. Strictly prevents look-ahead bias
by requiring that any broken swing was already confirmed (bar >= confirmed_index)
before testing for structural breaks.
"""

from __future__ import annotations

from typing import List, Optional, Tuple
import pandas as pd

from src.ict.models import (
    BreakType,
    MarketTrend,
    StructureBreak,
    SwingPoint,
    SwingType,
)


def detect_market_structure(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    break_on_close: bool = True,
) -> Tuple[List[StructureBreak], MarketTrend]:
    """
    Detect BOS and CHoCH structural transitions along a price series.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV market dataframe.
    swings : List[SwingPoint]
        List of confirmed swing points from `detect_swing_points`.
    break_on_close : bool, default True
        If True, requires candle Close beyond the swing level (institutional rule).
        If False, wick penetration is sufficient.

    Returns
    -------
    Tuple[List[StructureBreak], MarketTrend]
        List of chronological structural breaks, and the final trend state.
    """
    if df.empty or not swings:
        return [], MarketTrend.NEUTRAL

    breaks: List[StructureBreak] = []
    current_trend: MarketTrend = MarketTrend.NEUTRAL

    # Index swings by their confirmation index
    confirmed_swings_by_idx: dict[int, List[SwingPoint]] = {}
    for s in swings:
        confirmed_swings_by_idx.setdefault(s.confirmed_index, []).append(s)

    active_high: Optional[SwingPoint] = None
    active_low: Optional[SwingPoint] = None

    n = len(df)
    times = df["time"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()

    for t in range(n):
        # 1. Register newly confirmed swings at this bar
        if t in confirmed_swings_by_idx:
            for s in confirmed_swings_by_idx[t]:
                if s.swing_type == SwingType.SWING_HIGH:
                    active_high = s
                elif s.swing_type == SwingType.SWING_LOW:
                    active_low = s

        # 2. Check for Bullish Structural Break (breaking above active_high)
        if active_high is not None and t > active_high.confirmed_index:
            price_to_test = closes[t] if break_on_close else highs[t]
            if price_to_test > active_high.price:
                # Is it trend continuation (BOS) or reversal (CHoCH)?
                is_continuation = current_trend == MarketTrend.BULLISH
                break_type = BreakType.BOS if is_continuation else BreakType.CHOCH
                resulting_trend = MarketTrend.BULLISH

                cand_time = pd.to_datetime(times[t], utc=True)
                s_break = StructureBreak(
                    break_type=break_type,
                    direction=MarketTrend.BULLISH,
                    broken_swing=active_high,
                    break_index=t,
                    break_time=cand_time,
                    break_price=float(price_to_test),
                    prior_trend=current_trend,
                    resulting_trend=resulting_trend,
                )
                breaks.append(s_break)
                current_trend = resulting_trend
                active_high = None  # Consume the broken high

        # 3. Check for Bearish Structural Break (breaking below active_low)
        if active_low is not None and t > active_low.confirmed_index:
            price_to_test = closes[t] if break_on_close else lows[t]
            if price_to_test < active_low.price:
                # Is it trend continuation (BOS) or reversal (CHoCH)?
                is_continuation = current_trend == MarketTrend.BEARISH
                break_type = BreakType.BOS if is_continuation else BreakType.CHOCH
                resulting_trend = MarketTrend.BEARISH

                cand_time = pd.to_datetime(times[t], utc=True)
                s_break = StructureBreak(
                    break_type=break_type,
                    direction=MarketTrend.BEARISH,
                    broken_swing=active_low,
                    break_index=t,
                    break_time=cand_time,
                    break_price=float(price_to_test),
                    prior_trend=current_trend,
                    resulting_trend=resulting_trend,
                )
                breaks.append(s_break)
                current_trend = resulting_trend
                active_low = None  # Consume the broken low

    return breaks, current_trend
