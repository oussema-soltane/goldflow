"""
Unit tests for Liquidity Sweeps and Market Structure Shift (MSS).

Verifies buy-side and sell-side sweeps (turtle soup / false breakouts)
and multi-element confluence shifts (sweep + opposing break + FVG).
"""

import pandas as pd
import pytest

from src.ict.liquidity import detect_liquidity_sweeps, detect_market_structure_shifts
from src.ict.models import (
    BreakType,
    MarketStructureShift,
    MarketTrend,
    StructureBreak,
    SweepType,
    SwingClassification,
    SwingPoint,
    SwingType,
)
from src.ict.swings import detect_swing_points
from tests.test_ict_structure import make_candle


class TestICTLiquidity:
    def test_buy_side_liquidity_sweep(self):
        """
        Verify Buy-Side Liquidity (BSL) sweep:
        - Confirmed Swing High at index 2 (price=2660.0, confirmed at 4)
        - Candle 5 wicks to 2665.0 (breaches high), but closes at 2658.0 (rejection)
        - Penetration = 5.0 points
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2645, 2650, 2642, 2648),  # 0
            make_candle("2026-03-02 08:15:00", 2648, 2655, 2646, 2653),  # 1
            make_candle("2026-03-02 08:30:00", 2653, 2660, 2650, 2656),  # 2 - SH (2660)
            make_candle("2026-03-02 08:45:00", 2656, 2652, 2644, 2646),  # 3
            make_candle("2026-03-02 09:00:00", 2646, 2648, 2640, 2644),  # 4 - Confirms SH at 4
            make_candle("2026-03-02 09:15:00", 2644, 2665, 2642, 2658),  # 5 - Wick 2665, Close 2658 -> Sweep!
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)

        sweeps = detect_liquidity_sweeps(df, swings)
        assert len(sweeps) == 1

        sweep = sweeps[0]
        assert sweep.sweep_type == SweepType.BUY_SIDE
        assert sweep.sweep_index == 5
        assert sweep.sweep_price == 2665.0
        assert sweep.close_price == 2658.0
        assert sweep.wick_penetration == 5.0
        assert sweep.swept_swing.price == 2660.0

    def test_sell_side_liquidity_sweep(self):
        """
        Verify Sell-Side Liquidity (SSL) sweep:
        - Confirmed Swing Low at index 2 (price=2630.0, confirmed at 4)
        - Candle 5 dips to 2624.0 (breaches low), but closes at 2634.0 (rejection)
        - Penetration = 6.0 points
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2645, 2648, 2640, 2642),  # 0
            make_candle("2026-03-02 08:15:00", 2642, 2644, 2636, 2638),  # 1
            make_candle("2026-03-02 08:30:00", 2638, 2640, 2630, 2635),  # 2 - SL (2630)
            make_candle("2026-03-02 08:45:00", 2635, 2642, 2633, 2640),  # 3
            make_candle("2026-03-02 09:00:00", 2640, 2645, 2634, 2642),  # 4 - Confirms SL at 4
            make_candle("2026-03-02 09:15:00", 2642, 2644, 2624, 2634),  # 5 - Low 2624, Close 2634 -> Sweep!
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)

        sweeps = detect_liquidity_sweeps(df, swings)
        assert len(sweeps) == 1

        sweep = sweeps[0]
        assert sweep.sweep_type == SweepType.SELL_SIDE
        assert sweep.sweep_index == 5
        assert sweep.sweep_price == 2624.0
        assert sweep.close_price == 2634.0
        assert sweep.wick_penetration == 6.0

    def test_market_structure_shift_detection(self):
        """
        Verify Market Structure Shift:
        - Sell-side sweep at bar 5
        - Followed by Bullish structural break at bar 7 (within 5 bars)
        - Shifts market direction to BULLISH
        """
        sh_dummy = SwingPoint(
            index=2,
            time=pd.to_datetime("2026-03-02 08:30:00", utc=True),
            price=2630.0,
            swing_type=SwingType.SWING_LOW,
            classification=SwingClassification.INITIAL,
            confirmed_index=4,
            confirmed_time=pd.to_datetime("2026-03-02 09:00:00", utc=True),
        )
        candles = [
            make_candle("2026-03-02 08:00:00", 2645, 2648, 2640, 2642),
            make_candle("2026-03-02 08:15:00", 2642, 2644, 2636, 2638),
            make_candle("2026-03-02 08:30:00", 2638, 2640, 2630, 2635),
            make_candle("2026-03-02 08:45:00", 2635, 2642, 2633, 2640),
            make_candle("2026-03-02 09:00:00", 2640, 2645, 2634, 2642),
            make_candle("2026-03-02 09:15:00", 2642, 2644, 2624, 2634),  # Sweep at 5
        ]
        df = pd.DataFrame(candles)
        sweeps = detect_liquidity_sweeps(df, [sh_dummy])

        mock_break = StructureBreak(
            break_type=BreakType.CHOCH,
            direction=MarketTrend.BULLISH,
            broken_swing=sh_dummy,
            break_index=7,
            break_time=pd.to_datetime("2026-03-02 09:45:00", utc=True),
            break_price=2655.0,
            prior_trend=MarketTrend.BEARISH,
            resulting_trend=MarketTrend.BULLISH,
        )

        shifts = detect_market_structure_shifts(sweeps, [mock_break], max_lag_bars=5)
        assert len(shifts) == 1
        assert shifts[0].direction == MarketTrend.BULLISH
        assert shifts[0].shift_index == 7
