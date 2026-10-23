"""
Unit tests for ICT Swing Detection & Market Structure Engine (BOS / CHoCH).

Uses hand-crafted, mathematically deterministic OHLC fixtures with UTC timestamps.
Verifies exact pattern recognition and guarantees zero look-ahead bias.
"""

import pandas as pd
import pytest

from src.ict.models import (
    BreakType,
    MarketTrend,
    SwingClassification,
    SwingType,
)
from src.ict.structure import detect_market_structure
from src.ict.swings import detect_swing_points


def make_candle(
    time_str: str,
    open_: float,
    high: float,
    low: float,
    close: float,
    tick_volume: int = 100,
) -> dict:
    return {
        "time": pd.to_datetime(time_str, utc=True),
        "open": float(open_),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "tick_volume": tick_volume,
        "spread": 15,
        "real_volume": 0,
    }


class TestICTSwingsAndStructure:
    def test_swing_detection_handcrafted(self):
        """
        Verify that a 5-bar fractal swing high at index 2 is accurately detected
        and confirmed at index 4 (window=2).
        """
        # Hand-crafted 7-bar sequence with a peak at index 2 (high=2660)
        # and a trough at index 4 (low=2635)
        candles = [
            make_candle("2026-03-02 08:00:00", 2645, 2650, 2642, 2648),  # 0
            make_candle("2026-03-02 08:15:00", 2648, 2655, 2646, 2653),  # 1
            make_candle("2026-03-02 08:30:00", 2653, 2660, 2650, 2655),  # 2 - SWING HIGH
            make_candle("2026-03-02 08:45:00", 2655, 2652, 2644, 2645),  # 3
            make_candle("2026-03-02 09:00:00", 2645, 2648, 2635, 2640),  # 4 - Confirms SH at 2
            make_candle("2026-03-02 09:15:00", 2640, 2646, 2638, 2644),  # 5
            make_candle("2026-03-02 09:30:00", 2644, 2650, 2642, 2649),  # 6 - Confirms SL at 4
        ]
        df = pd.DataFrame(candles)

        swings = detect_swing_points(df, window=2)
        assert len(swings) >= 2

        # 1. Swing High at index 2
        sh = next(s for s in swings if s.swing_type == SwingType.SWING_HIGH)
        assert sh.index == 2
        assert sh.price == 2660.0
        assert sh.confirmed_index == 4  # index 2 + window 2 = 4
        assert sh.confirmed_time == pd.to_datetime("2026-03-02 09:00:00", utc=True)

        # 2. Swing Low at index 4
        sl = next(s for s in swings if s.swing_type == SwingType.SWING_LOW)
        assert sl.index == 4
        assert sl.price == 2635.0
        assert sl.confirmed_index == 6
        assert sl.confirmed_time == pd.to_datetime("2026-03-02 09:30:00", utc=True)

    def test_swing_lookahead_prevention(self):
        """
        Verify that swing points cannot be confirmed before i + window.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2645, 2650, 2640, 2648),
            make_candle("2026-03-02 08:15:00", 2648, 2652, 2645, 2650),
            make_candle("2026-03-02 08:30:00", 2650, 2670, 2648, 2665),  # High at 2
            make_candle("2026-03-02 08:45:00", 2665, 2662, 2655, 2658),
            make_candle("2026-03-02 09:00:00", 2658, 2655, 2650, 2652),  # Confirms at 4
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)

        for s in swings:
            # Confirmed index must be strictly greater than candidate index
            assert s.confirmed_index == s.index + 2
            assert s.confirmed_index > s.index

    def test_bullish_bos_continuation(self):
        """
        Construct a sequence:
        1. Bullish break (CHoCH to start Bull trend)
        2. High formed at index 2 (2660)
        3. Confirmed at index 4
        4. Breakout above 2660 at index 5 with close=2665 -> BOS (Bullish continuation)
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2630, 2635, 2625, 2632),  # 0
            make_candle("2026-03-02 08:15:00", 2632, 2640, 2630, 2638),  # 1
            make_candle("2026-03-02 08:30:00", 2638, 2650, 2635, 2645),  # 2 - SH1 (2650)
            make_candle("2026-03-02 08:45:00", 2645, 2642, 2635, 2638),  # 3
            make_candle("2026-03-02 09:00:00", 2638, 2640, 2632, 2636),  # 4 - Confirms SH1
            make_candle("2026-03-02 09:15:00", 2636, 2655, 2634, 2654),  # 5 - Breaks SH1 -> CHoCH (Bull)
            make_candle("2026-03-02 09:30:00", 2654, 2660, 2650, 2658),  # 6 - SH2 (2660)
            make_candle("2026-03-02 09:45:00", 2658, 2655, 2648, 2650),  # 7
            make_candle("2026-03-02 10:00:00", 2650, 2652, 2645, 2648),  # 8 - Confirms SH2
            make_candle("2026-03-02 10:15:00", 2648, 2670, 2647, 2668),  # 9 - Closes above 2660 -> BOS!
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)
        breaks, trend = detect_market_structure(df, swings, break_on_close=True)

        assert len(breaks) >= 2
        # First break is CHoCH into bullish
        assert breaks[0].break_type == BreakType.CHOCH
        assert breaks[0].direction == MarketTrend.BULLISH
        assert breaks[0].break_index == 5

        # Second break is BOS continuing bullish
        assert breaks[1].break_type == BreakType.BOS
        assert breaks[1].direction == MarketTrend.BULLISH
        assert breaks[1].break_index == 9
        assert breaks[1].break_price == 2668.0
        assert trend == MarketTrend.BULLISH

    def test_choch_reversal(self):
        """
        Verify Change of Character from Bullish to Bearish:
        Price establishes a Bullish trend, but then closes below a confirmed Higher Low.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2645, 2655, 2642, 2650),  # 0
            make_candle("2026-03-02 08:15:00", 2650, 2658, 2646, 2655),  # 1
            make_candle("2026-03-02 08:30:00", 2650, 2652, 2630, 2635),  # 2 - SL1 (low=2630)
            make_candle("2026-03-02 08:45:00", 2635, 2648, 2634, 2646),  # 3
            make_candle("2026-03-02 09:00:00", 2646, 2652, 2640, 2650),  # 4 - Confirms SL1 at 4
            make_candle("2026-03-02 09:15:00", 2650, 2665, 2648, 2662),  # 5 - SH1 (high=2665)
            make_candle("2026-03-02 09:30:00", 2662, 2660, 2652, 2655),  # 6
            make_candle("2026-03-02 09:45:00", 2655, 2658, 2650, 2654),  # 7 - Confirms SH1 at 7
            make_candle("2026-03-02 10:00:00", 2654, 2668, 2652, 2667),  # 8 - Closes 2667 > 2665 -> Bullish!
            make_candle("2026-03-02 10:15:00", 2667, 2665, 2620, 2625),  # 9 - Closes 2625 < 2630 -> Bearish CHoCH!
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)
        breaks, trend = detect_market_structure(df, swings, break_on_close=True)

        choch_breaks = [b for b in breaks if b.break_type == BreakType.CHOCH and b.direction == MarketTrend.BEARISH]
        assert len(choch_breaks) >= 1
        choch = choch_breaks[0]
        assert choch.break_index == 9
        assert choch.break_price == 2625.0
        assert trend == MarketTrend.BEARISH

    def test_break_on_close_vs_wick_filtration(self):
        """
        Verify that a wick exceeding a swing level without closing beyond it
        does NOT trigger a structural break when break_on_close=True.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2645, 2638, 2642),  # 0
            make_candle("2026-03-02 08:15:00", 2642, 2648, 2640, 2646),  # 1
            make_candle("2026-03-02 08:30:00", 2646, 2660, 2644, 2650),  # 2 - SH (2660)
            make_candle("2026-03-02 08:45:00", 2650, 2652, 2642, 2645),  # 3
            make_candle("2026-03-02 09:00:00", 2645, 2648, 2640, 2644),  # 4 - Confirms SH
            # Candle 5 wicks to 2663 (above 2660) but closes at 2655 (below 2660)
            make_candle("2026-03-02 09:15:00", 2644, 2663, 2642, 2655),  # 5 - Wick break only
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)

        # 1. break_on_close=True -> NO structural break
        breaks_close, _ = detect_market_structure(df, swings, break_on_close=True)
        assert len(breaks_close) == 0

        # 2. break_on_close=False -> Triggers break on wick
        breaks_wick, _ = detect_market_structure(df, swings, break_on_close=False)
        assert len(breaks_wick) == 1
        assert breaks_wick[0].break_index == 5
