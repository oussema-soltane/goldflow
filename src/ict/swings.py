"""
Fractal Swing High and Swing Low Detection Engine.

Detects local price extrema using a configurable window parameter.
Enforces zero look-ahead bias by tracking the exact future confirmation index
(i + window) when the swing point became known to the market.
"""

from __future__ import annotations

from typing import List, Optional
import pandas as pd

from src.ict.models import SwingClassification, SwingPoint, SwingType


def detect_swing_points(
    df: pd.DataFrame,
    window: int = 2,
) -> List[SwingPoint]:
    """
    Identify fractal swing highs and swing lows across a price series.

    Parameters
    ----------
    df : pd.DataFrame
        Market dataframe containing ['time', 'high', 'low'] columns.
        Must be sorted chronologically.
    window : int, default 2
        Number of adjacent bars required on both sides of a candidate swing.
        `window=2` yields a classical 5-bar institutional fractal (2 left, 1 center, 2 right).

    Returns
    -------
    List[SwingPoint]
        Chronologically ordered list of confirmed swing points.
    """
    if window < 1:
        raise ValueError(f"Swing window must be at least 1, got {window}")
    if df.empty or len(df) < (2 * window + 1):
        return []

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    times = df["time"].to_numpy()
    n = len(df)

    swing_points: List[SwingPoint] = []
    last_sh: Optional[SwingPoint] = None
    last_sl: Optional[SwingPoint] = None

    for i in range(window, n - window):
        curr_high = highs[i]
        curr_low = lows[i]

        # 1. Check Swing High: strictly higher than left and right neighbors
        is_sh = True
        for j in range(1, window + 1):
            if highs[i - j] >= curr_high or highs[i + j] >= curr_high:
                is_sh = False
                break

        # 2. Check Swing Low: strictly lower than left and right neighbors
        is_sl = True
        for j in range(1, window + 1):
            if lows[i - j] <= curr_low or lows[i + j] <= curr_low:
                is_sl = False
                break

        conf_idx = i + window
        conf_time = pd.to_datetime(times[conf_idx], utc=True)
        cand_time = pd.to_datetime(times[i], utc=True)

        if is_sh:
            classification = SwingClassification.INITIAL
            if last_sh is not None:
                classification = (
                    SwingClassification.HIGHER_HIGH
                    if curr_high > last_sh.price
                    else SwingClassification.LOWER_HIGH
                )

            sh = SwingPoint(
                index=i,
                time=cand_time,
                price=float(curr_high),
                swing_type=SwingType.SWING_HIGH,
                classification=classification,
                confirmed_index=conf_idx,
                confirmed_time=conf_time,
            )
            swing_points.append(sh)
            last_sh = sh

        if is_sl:
            classification = SwingClassification.INITIAL
            if last_sl is not None:
                classification = (
                    SwingClassification.LOWER_LOW
                    if curr_low < last_sl.price
                    else SwingClassification.HIGHER_LOW
                )

            sl = SwingPoint(
                index=i,
                time=cand_time,
                price=float(curr_low),
                swing_type=SwingType.SWING_LOW,
                classification=classification,
                confirmed_index=conf_idx,
                confirmed_time=conf_time,
            )
            swing_points.append(sl)
            last_sl = sl

    # Sort swing points primarily by candidate index
    swing_points.sort(key=lambda s: s.index)
    return swing_points
