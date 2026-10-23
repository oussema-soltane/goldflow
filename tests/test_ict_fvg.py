"""
Unit tests for Fair Value Gap (FVG) and Displacement Detection Engine.

Uses hand-crafted OHLC fixtures with exact mathematical values to verify:
- Bullish FVG boundary calculation and Consequent Encroachment (50% CE).
- Bearish FVG boundary calculation and CE.
- Mitigation state lifecycle (UNTESTED -> PARTIALLY_MITIGATED -> FULLY_MITIGATED).
- Displacement candle classification against ATR.
"""

import pandas as pd
import pytest

from src.ict.fvg import detect_displacements, detect_fair_value_gaps
from src.ict.models import FVGStatus, FVGType
from tests.test_ict_structure import make_candle


class TestICTFairValueGaps:
    def test_bullish_fvg_detection(self):
        """
        Verify Bullish FVG detection:
        Candle 0: High = 2645.0
        Candle 1: Strong bullish impulse
        Candle 2: Low = 2655.0
        Imbalance: Low[2] (2655) > High[0] (2645)
        Top = 2655, Bottom = 2645, CE = 2650, Size = 10.0
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2645, 2638, 2644),  # 0: High 2645
            make_candle("2026-03-02 08:15:00", 2644, 2660, 2643, 2658),  # 1: Impulse
            make_candle("2026-03-02 08:30:00", 2658, 2665, 2655, 2663),  # 2: Low 2655
        ]
        df = pd.DataFrame(candles)

        fvgs = detect_fair_value_gaps(df, min_gap_points=0.0)
        assert len(fvgs) == 1

        fvg = fvgs[0]
        assert fvg.gap_type == FVGType.BULLISH
        assert fvg.candle_index == 1
        assert fvg.creation_index == 2
        assert fvg.bottom_price == 2645.0
        assert fvg.top_price == 2655.0
        assert fvg.consequent_encroachment == 2650.0
        assert fvg.size == 10.0
        assert fvg.status == FVGStatus.UNTESTED

    def test_bearish_fvg_detection(self):
        """
        Verify Bearish FVG detection:
        Candle 0: Low = 2650.0
        Candle 1: Strong bearish impulse
        Candle 2: High = 2638.0
        Imbalance: High[2] (2638) < Low[0] (2650)
        Top = 2650, Bottom = 2638, CE = 2644, Size = 12.0
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2655, 2658, 2650, 2652),  # 0: Low 2650
            make_candle("2026-03-02 08:15:00", 2652, 2653, 2632, 2635),  # 1: Impulse
            make_candle("2026-03-02 08:30:00", 2635, 2638, 2628, 2630),  # 2: High 2638
        ]
        df = pd.DataFrame(candles)

        fvgs = detect_fair_value_gaps(df, min_gap_points=0.0)
        assert len(fvgs) == 1

        fvg = fvgs[0]
        assert fvg.gap_type == FVGType.BEARISH
        assert fvg.candle_index == 1
        assert fvg.creation_index == 2
        assert fvg.top_price == 2650.0
        assert fvg.bottom_price == 2638.0
        assert fvg.consequent_encroachment == 2644.0
        assert fvg.size == 12.0
        assert fvg.status == FVGStatus.UNTESTED

    def test_fvg_mitigation_lifecycle(self):
        """
        Trace FVG status progression forward in time:
        - Bar 2: FVG created between [2645, 2655], CE=2650
        - Bar 3: Price stays above gap (UNTESTED)
        - Bar 4: Price dips to 2648 (touches CE -> PARTIALLY_MITIGATED)
        - Bar 5: Price plunges and closes at 2640 < 2645 (FULLY_MITIGATED)
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2645, 2638, 2644),  # 0
            make_candle("2026-03-02 08:15:00", 2644, 2660, 2643, 2658),  # 1
            make_candle("2026-03-02 08:30:00", 2658, 2665, 2655, 2663),  # 2 - FVG created [2645, 2655]
            make_candle("2026-03-02 08:45:00", 2663, 2668, 2660, 2665),  # 3 - Stays above
            make_candle("2026-03-02 09:00:00", 2665, 2666, 2648, 2652),  # 4 - Low 2648 <= CE 2650
            make_candle("2026-03-02 09:15:00", 2652, 2653, 2638, 2640),  # 5 - Close 2640 < 2645 -> Full
        ]
        df = pd.DataFrame(candles)

        fvgs = detect_fair_value_gaps(df, track_mitigation=True)
        bullish_fvgs = [f for f in fvgs if f.gap_type == FVGType.BULLISH]
        assert len(bullish_fvgs) == 1
        assert bullish_fvgs[0].status == FVGStatus.FULLY_MITIGATED
        assert bullish_fvgs[0].mitigation_index == 5

    def test_min_gap_filter(self):
        """Verify that negligible gaps below min_gap_points are omitted."""
        candles = [
            make_candle("2026-03-02 08:00:00", 2650.0, 2652.0, 2648.0, 2651.0),
            make_candle("2026-03-02 08:15:00", 2651.0, 2655.0, 2650.0, 2654.0),
            # Gap between High[0]=2652.0 and Low[2]=2652.5 is only 0.5 points
            make_candle("2026-03-02 08:30:00", 2654.0, 2658.0, 2652.5, 2656.0),
        ]
        df = pd.DataFrame(candles)

        # Threshold 1.0 points -> 0.5 points should be ignored
        fvgs = detect_fair_value_gaps(df, min_gap_points=1.0)
        assert len(fvgs) == 0

        # Threshold 0.2 points -> 0.5 points is detected
        fvgs_low = detect_fair_value_gaps(df, min_gap_points=0.2)
        assert len(fvgs_low) == 1
        assert fvgs_low[0].size == 0.5

    def test_displacement_detection(self):
        """
        Verify institutional displacement candle detection against rolling ATR.
        """
        records = []
        # Create 14 baseline calm candles with ~2 pt range
        for i in range(14):
            records.append(
                make_candle(f"2026-03-02 {8 + i // 4:02d}:{(i % 4) * 15:02d}:00", 2650, 2652, 2649, 2651)
            )

        # Candle 14 is an explosive displacement candle: range=12 pts, body=10 pts
        records.append(
            make_candle("2026-03-02 11:30:00", 2651, 2663, 2650, 2661)
        )
        df = pd.DataFrame(records)

        displacements = detect_displacements(df, atr_period=14, multiplier=1.5, min_body_ratio=0.6)
        assert len(displacements) >= 1
        assert 14 in displacements
