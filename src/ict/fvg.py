"""
Fair Value Gap (FVG) and Institutional Displacement Engine.

Detects 3-candle imbalance zones (Bullish and Bearish FVGs), calculates Consequent
Encroachment (50% midpoint), tracks forward mitigation without look-ahead bias,
and identifies energetic displacement candles.
"""

from __future__ import annotations

from typing import List, Optional
import numpy as np
import pandas as pd

from src.ict.models import FVGStatus, FVGType, FairValueGap


def detect_fair_value_gaps(
    df: pd.DataFrame,
    min_gap_points: float = 0.0,
    track_mitigation: bool = True,
) -> List[FairValueGap]:
    """
    Detect 3-candle Fair Value Gaps across a price series.

    Formulas
    --------
    Bullish FVG: Low[i+1] > High[i-1]
        Top = Low[i+1], Bottom = High[i-1], CE = (Top + Bottom) / 2
    Bearish FVG: High[i+1] < Low[i-1]
        Top = Low[i-1], Bottom = High[i+1], CE = (Top + Bottom) / 2

    Confirmation: Occurs at bar i+1 upon completion of candle i+1.

    Parameters
    ----------
    df : pd.DataFrame
        OHLC dataframe sorted chronologically.
    min_gap_points : float, default 0.0
        Minimum gap height (in price units) required to qualify as an institutional FVG.
    track_mitigation : bool, default True
        Whether to trace forward in time to determine if subsequent candles
        mitigate or invalidate the gap.

    Returns
    -------
    List[FairValueGap]
        List of identified Fair Value Gaps.
    """
    if df.empty or len(df) < 3:
        return []

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    times = df["time"].to_numpy()
    n = len(df)

    fvgs: List[FairValueGap] = []

    for i in range(1, n - 1):
        prev_high = highs[i - 1]
        prev_low = lows[i - 1]
        next_high = highs[i + 1]
        next_low = lows[i + 1]

        conf_idx = i + 1
        conf_time = pd.to_datetime(times[conf_idx], utc=True)

        # 1. Bullish FVG: Low of candle i+1 is strictly above High of candle i-1
        if next_low > prev_high:
            gap_size = float(next_low - prev_high)
            if gap_size >= min_gap_points:
                top = float(next_low)
                bottom = float(prev_high)
                ce = float((top + bottom) / 2.0)
                fvg = FairValueGap(
                    gap_type=FVGType.BULLISH,
                    candle_index=i,
                    creation_index=conf_idx,
                    creation_time=conf_time,
                    top_price=top,
                    bottom_price=bottom,
                    consequent_encroachment=ce,
                    size=gap_size,
                    status=FVGStatus.UNTESTED,
                )
                fvgs.append(fvg)

        # 2. Bearish FVG: High of candle i+1 is strictly below Low of candle i-1
        elif next_high < prev_low:
            gap_size = float(prev_low - next_high)
            if gap_size >= min_gap_points:
                top = float(prev_low)
                bottom = float(next_high)
                ce = float((top + bottom) / 2.0)
                fvg = FairValueGap(
                    gap_type=FVGType.BEARISH,
                    candle_index=i,
                    creation_index=conf_idx,
                    creation_time=conf_time,
                    top_price=top,
                    bottom_price=bottom,
                    consequent_encroachment=ce,
                    size=gap_size,
                    status=FVGStatus.UNTESTED,
                )
                fvgs.append(fvg)

    # 3. Track mitigation forward in time
    if track_mitigation:
        for fvg in fvgs:
            # Mitigation can only occur at bars subsequent to creation_index
            for k in range(fvg.creation_index + 1, n):
                k_high = highs[k]
                k_low = lows[k]
                k_close = closes[k]
                k_time = pd.to_datetime(times[k], utc=True)

                if fvg.gap_type == FVGType.BULLISH:
                    # Touched or entered gap
                    if k_low <= fvg.top_price:
                        if k_close < fvg.bottom_price or k_low <= fvg.bottom_price:
                            fvg.status = FVGStatus.FULLY_MITIGATED
                            fvg.mitigation_index = k
                            fvg.mitigation_time = k_time
                            break
                        else:
                            fvg.status = FVGStatus.PARTIALLY_MITIGATED
                            if fvg.mitigation_index is None:
                                fvg.mitigation_index = k
                                fvg.mitigation_time = k_time

                elif fvg.gap_type == FVGType.BEARISH:
                    # Touched or entered gap
                    if k_high >= fvg.bottom_price:
                        if k_close > fvg.top_price or k_high >= fvg.top_price:
                            fvg.status = FVGStatus.FULLY_MITIGATED
                            fvg.mitigation_index = k
                            fvg.mitigation_time = k_time
                            break
                        else:
                            fvg.status = FVGStatus.PARTIALLY_MITIGATED
                            if fvg.mitigation_index is None:
                                fvg.mitigation_index = k
                                fvg.mitigation_time = k_time

    return fvgs


def detect_displacements(
    df: pd.DataFrame,
    atr_period: int = 14,
    multiplier: float = 1.5,
    min_body_ratio: float = 0.6,
) -> List[int]:
    """
    Identify bars exhibiting institutional displacement (large body relative to ATR).

    Parameters
    ----------
    df : pd.DataFrame
        OHLC market dataframe.
    atr_period : int, default 14
        ATR rolling lookback window.
    multiplier : float, default 1.5
        Threshold multiplier against rolling ATR.
    min_body_ratio : float, default 0.6
        Minimum body / total_range ratio to filter out high-wick candles.

    Returns
    -------
    List[int]
        Positional indices of displacement candles.
    """
    if df.empty or len(df) < (atr_period + 1):
        return []

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    n = len(df)

    # Calculate True Range
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    # Rolling ATR of preceding bars (uncontaminated by candidate candle's own expansion)
    atr = pd.Series(tr).rolling(window=atr_period, min_periods=atr_period).mean().to_numpy()

    displacement_indices: List[int] = []

    for i in range(atr_period, n):
        baseline_atr = atr[i - 1]
        if np.isnan(baseline_atr) or baseline_atr <= 0:
            continue

        body = abs(closes[i] - opens[i])
        candle_range = highs[i] - lows[i]

        if candle_range <= 0:
            continue

        body_ratio = body / candle_range
        if body >= (multiplier * baseline_atr) and body_ratio >= min_body_ratio:
            displacement_indices.append(i)

    return displacement_indices
