"""
Institutional Order Block (OB) Detection Engine.

Identifies the origin candles of institutional displacement that produce
Fair Value Gaps or structural breaks, and tracks forward mitigation and invalidation.
"""

from __future__ import annotations

from typing import List, Optional
import pandas as pd

from src.ict.models import (
    FairValueGap,
    FVGType,
    OrderBlock,
    OrderBlockType,
    StructureBreak,
)


def detect_order_blocks(
    df: pd.DataFrame,
    fvgs: Optional[List[FairValueGap]] = None,
    structure_breaks: Optional[List[StructureBreak]] = None,
    track_mitigation: bool = True,
) -> List[OrderBlock]:
    """
    Identify Bullish and Bearish Order Blocks.

    - Bullish OB: The last down-close candle (close < open) prior to a bullish displacement / FVG.
    - Bearish OB: The last up-close candle (close > open) prior to a bearish displacement / FVG.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV market dataframe.
    fvgs : List[FairValueGap], optional
        Detected FVGs used to confirm displacement origin.
    structure_breaks : List[StructureBreak], optional
        Detected structural breaks.
    track_mitigation : bool, default True
        Whether to trace forward in time for mitigation or invalidation.

    Returns
    -------
    List[OrderBlock]
        List of identified Order Blocks.
    """
    if df.empty or len(df) < 3:
        return []

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    volumes = df["tick_volume"].to_numpy() if "tick_volume" in df.columns else [0.0] * len(df)
    times = df["time"].to_numpy()
    n = len(df)

    order_blocks: List[OrderBlock] = []
    seen_indices = set()

    # 1. Detect OBs from FVGs (primary institutional signature)
    if fvgs:
        for fvg in fvgs:
            # The FVG is confirmed by its third candle (creation_index). Search
            # backward from that completed displacement/confirmation candle so the
            # middle candle of the 3-candle pattern is considered first.
            c_idx = fvg.creation_index
            # Look backwards from displacement candle to find last opposing candle
            lookback = 1
            while c_idx - lookback >= 0 and lookback <= 3:
                cand_idx = c_idx - lookback
                is_down = closes[cand_idx] < opens[cand_idx]
                is_up = closes[cand_idx] > opens[cand_idx]

                if fvg.gap_type == FVGType.BULLISH and is_down:
                    if cand_idx not in seen_indices:
                        ob = OrderBlock(
                            ob_type=OrderBlockType.BULLISH,
                            candle_index=cand_idx,
                            candle_time=pd.to_datetime(times[cand_idx], utc=True),
                            high=float(highs[cand_idx]),
                            low=float(lows[cand_idx]),
                            open=float(opens[cand_idx]),
                            close=float(closes[cand_idx]),
                            volume=float(volumes[cand_idx]),
                            confirmed_index=fvg.creation_index,
                            confirmed_time=fvg.creation_time,
                            fvg_index=fvg.candle_index,
                        )
                        order_blocks.append(ob)
                        seen_indices.add(cand_idx)
                    break

                elif fvg.gap_type == FVGType.BEARISH and is_up:
                    if cand_idx not in seen_indices:
                        ob = OrderBlock(
                            ob_type=OrderBlockType.BEARISH,
                            candle_index=cand_idx,
                            candle_time=pd.to_datetime(times[cand_idx], utc=True),
                            high=float(highs[cand_idx]),
                            low=float(lows[cand_idx]),
                            open=float(opens[cand_idx]),
                            close=float(closes[cand_idx]),
                            volume=float(volumes[cand_idx]),
                            confirmed_index=fvg.creation_index,
                            confirmed_time=fvg.creation_time,
                            fvg_index=fvg.candle_index,
                        )
                        order_blocks.append(ob)
                        seen_indices.add(cand_idx)
                    break

                lookback += 1

    # 2. Track mitigation and invalidation forward in time
    if track_mitigation:
        for ob in order_blocks:
            # Mitigation & invalidation testing strictly begins AFTER confirmation
            start_test = ob.confirmed_index + 1
            for k in range(start_test, n):
                k_high = highs[k]
                k_low = lows[k]
                k_close = closes[k]
                k_time = pd.to_datetime(times[k], utc=True)

                if ob.ob_type == OrderBlockType.BULLISH:
                    # Invalidation: candle closes below OB low
                    if k_close < ob.low:
                        ob.is_invalidated = True
                        ob.invalidation_index = k
                        ob.invalidation_time = k_time
                        if not ob.is_mitigated:
                            ob.is_mitigated = True
                            ob.mitigation_index = k
                            ob.mitigation_time = k_time
                        break
                    # Mitigation: price wicks or trades into OB zone
                    elif k_low <= ob.high:
                        ob.is_mitigated = True
                        if ob.mitigation_index is None:
                            ob.mitigation_index = k
                            ob.mitigation_time = k_time

                elif ob.ob_type == OrderBlockType.BEARISH:
                    # Invalidation: candle closes above OB high
                    if k_close > ob.high:
                        ob.is_invalidated = True
                        ob.invalidation_index = k
                        ob.invalidation_time = k_time
                        if not ob.is_mitigated:
                            ob.is_mitigated = True
                            ob.mitigation_index = k
                            ob.mitigation_time = k_time
                        break
                    # Mitigation: price wicks or trades into OB zone
                    elif k_high >= ob.low:
                        ob.is_mitigated = True
                        if ob.mitigation_index is None:
                            ob.mitigation_index = k
                            ob.mitigation_time = k_time

    order_blocks.sort(key=lambda x: x.candle_index)
    return order_blocks
