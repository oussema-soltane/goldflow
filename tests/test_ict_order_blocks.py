"""
Unit tests for Institutional Order Block (OB) Engine.

Verifies identification of origin displacement candles and forward mitigation testing.
"""

import pandas as pd
import pytest

from src.ict.fvg import detect_fair_value_gaps
from src.ict.models import OrderBlockType
from src.ict.order_blocks import detect_order_blocks
from tests.test_ict_structure import make_candle


class TestICTOrderBlocks:
    def test_bullish_order_block(self):
        """
        Verify Bullish Order Block:
        - Candle 0: Bearish down-candle (Open 2646, Close 2640, Low 2638, High 2647)
        - Candle 1: Bullish impulse (Open 2640, Close 2658)
        - Candle 2: High candle (Low 2652 > High[0] 2647 -> Bullish FVG)
        - Candle 0 must be identified as Bullish OB
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2646, 2647, 2638, 2640),  # 0: Down candle (OB)
            make_candle("2026-03-02 08:15:00", 2640, 2660, 2639, 2658),  # 1: Impulse
            make_candle("2026-03-02 08:30:00", 2658, 2665, 2652, 2663),  # 2: Low 2652 > High 2647 (FVG)
        ]
        df = pd.DataFrame(candles)

        fvgs = detect_fair_value_gaps(df)
        assert len(fvgs) == 1

        obs = detect_order_blocks(df, fvgs=fvgs)
        assert len(obs) == 1

        ob = obs[0]
        assert ob.ob_type == OrderBlockType.BULLISH
        assert ob.candle_index == 0
        assert ob.high == 2647.0
        assert ob.low == 2638.0
        assert ob.open == 2646.0
        assert ob.close == 2640.0
        assert ob.is_mitigated is False

    def test_bearish_order_block(self):
        """
        Verify Bearish Order Block:
        - Candle 0: Bullish up-candle (Open 2650, Close 2656, Low 2648, High 2658)
        - Candle 1: Bearish impulse (Open 2656, Close 2638)
        - Candle 2: Low candle (High 2644 < Low[0] 2648 -> Bearish FVG)
        - Candle 0 must be identified as Bearish OB
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2650, 2658, 2648, 2656),  # 0: Up candle (OB)
            make_candle("2026-03-02 08:15:00", 2656, 2657, 2636, 2638),  # 1: Impulse
            make_candle("2026-03-02 08:30:00", 2638, 2644, 2632, 2635),  # 2: High 2644 < Low 2648 (FVG)
        ]
        df = pd.DataFrame(candles)

        fvgs = detect_fair_value_gaps(df)
        assert len(fvgs) == 1

        obs = detect_order_blocks(df, fvgs=fvgs)
        assert len(obs) == 1

        ob = obs[0]
        assert ob.ob_type == OrderBlockType.BEARISH
        assert ob.candle_index == 0
        assert ob.high == 2658.0
        assert ob.low == 2648.0
        assert ob.open == 2650.0
        assert ob.close == 2656.0

    def test_order_block_mitigation(self):
        """
        Verify that a future candle dipping into the Order Block zone
        marks the OB as mitigated.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2646, 2647, 2638, 2640),  # 0: OB zone [2638, 2647]
            make_candle("2026-03-02 08:15:00", 2640, 2660, 2639, 2658),  # 1: Impulse
            make_candle("2026-03-02 08:30:00", 2658, 2665, 2652, 2663),  # 2: FVG
            make_candle("2026-03-02 08:45:00", 2663, 2664, 2645, 2648),  # 3: Dips to Low 2645 <= OB.high 2647!
        ]
        df = pd.DataFrame(candles)

        fvgs = detect_fair_value_gaps(df)
        obs = detect_order_blocks(df, fvgs=fvgs, track_mitigation=True)
        assert len(obs) == 1
        assert obs[0].is_mitigated is True
        assert obs[0].mitigation_index == 3

    def test_last_opposing_middle_candle_is_selected(self):
        """The FVG middle candle is eligible as the nearest opposing candle."""
        candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2650, 2638, 2645),  # 0: bullish
            make_candle("2026-03-02 08:15:00", 2658, 2660, 2648, 2652),  # 1: bearish, latest opposing candle
            make_candle("2026-03-02 08:30:00", 2652, 2665, 2652, 2663),  # 2: confirms bullish FVG
        ]
        df = pd.DataFrame(candles)
        fvgs = detect_fair_value_gaps(df)
        assert len(fvgs) == 1
        obs = detect_order_blocks(df, fvgs=fvgs, track_mitigation=False)
        assert len(obs) == 1
        assert obs[0].ob_type == OrderBlockType.BULLISH
        assert obs[0].candle_index == 1
        assert obs[0].confirmed_index == 2
