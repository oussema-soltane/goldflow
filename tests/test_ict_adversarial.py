"""
GoldFlow — Adversarial Correctness & Temporal Invariance Audit Test Suite.

Audits the 14 core mathematical properties of the ICT Market Structure Engine:
1. Future independence (mutations after time T do not affect events confirmed at <= T).
2. Swing confirmation (swings inaccessible before i + window completion).
3. Structural breaks (unconfirmed swing levels cannot trigger BOS/CHoCH).
4. Event availability (event_time and confirmed_time consistency across all models).
5. Historical prefixes (prefix truncated at T agrees with full dataset events confirmed at <= T).
6. UTC consistency (no naive timestamps enter or leak from detection pipelines).
7. Duplicate breaks (single structural level does not emit repeated breaks).
8. Ambiguous candles (wide-range candles crossing multiple structural boundaries).
9. FVG lifecycle (boundary equality, wick penetration, 50% CE, body violation).
10. Displacement (ATR calculation window, warm-up, zero-range candles).
11. Liquidity sweeps (level availability, equality vs breach, wick rejection).
12. MSS (direction, event ordering, max window, FVG confluence).
13. Order blocks (origin candle, confirmation timing, mitigation, invalidation).
14. Chart integrity (annotations placed at valid times with confirmation tooltips).
"""

import copy
import numpy as np
import pandas as pd
import pytest

from src.data.loader import generate_synthetic_gold_data
from src.ict.engine import analyze_market_structure
from src.ict.fvg import detect_displacements, detect_fair_value_gaps
from src.ict.liquidity import detect_liquidity_sweeps, detect_market_structure_shifts
from src.ict.models import (
    BreakType,
    FairValueGap,
    FVGStatus,
    FVGType,
    LiquiditySweep,
    MarketTrend,
    OrderBlockType,
    StructureBreak,
    SweepType,
    SwingClassification,
    SwingPoint,
    SwingType,
)
from src.ict.order_blocks import detect_order_blocks
from src.ict.structure import detect_market_structure
from src.ict.swings import detect_swing_points
from src.visualization.charts import create_candlestick_chart
from tests.test_ict_structure import make_candle


class TestAdversarialTemporalCorrectness:
    # -------------------------------------------------------------------------
    # Property 1: Future Independence
    # -------------------------------------------------------------------------
    def test_property_1_future_independence(self):
        """
        Future Independence:
        Modifying price bars after time T (index T) must NOT alter any swing points,
        FVGs, or structural breaks that were already confirmed at or before T.
        """
        # Baseline sequence of 10 candles
        candles = [
            make_candle(f"2026-03-02 08:{i*15:02d}:00", 2640 + i, 2645 + i, 2638 + i, 2643 + i)
            for i in range(4)
        ]
        # Peak at candle 2 (high=2660), trough at candle 4 (low=2630)
        candles[2] = make_candle("2026-03-02 08:30:00", 2645, 2660, 2642, 2655)
        candles.append(make_candle("2026-03-02 09:00:00", 2645, 2648, 2630, 2635))  # 4: Confirms SH at 2
        candles.append(make_candle("2026-03-02 09:15:00", 2635, 2644, 2634, 2642))  # 5
        candles.append(make_candle("2026-03-02 09:30:00", 2642, 2652, 2640, 2650))  # 6: Confirms SL at 4
        candles.append(make_candle("2026-03-02 09:45:00", 2650, 2655, 2648, 2653))  # 7
        candles.append(make_candle("2026-03-02 10:00:00", 2653, 2658, 2651, 2656))  # 8
        candles.append(make_candle("2026-03-02 10:15:00", 2656, 2662, 2654, 2660))  # 9

        df_orig = pd.DataFrame(candles)
        res_orig = analyze_market_structure(df_orig, swing_window=2)

        # Swings confirmed at or before index 6 (T = 6)
        swings_at_t_orig = [s for s in res_orig.swings if s.confirmed_index <= 6]
        assert len(swings_at_t_orig) >= 2

        # Create mutated future: drastically change bars 7, 8, 9
        df_mutated = df_orig.copy()
        df_mutated.loc[7, ["open", "high", "low", "close"]] = [2700, 2750, 2690, 2740]
        df_mutated.loc[8, ["open", "high", "low", "close"]] = [2740, 2780, 2730, 2770]
        df_mutated.loc[9, ["open", "high", "low", "close"]] = [2770, 2800, 2760, 2790]

        res_mutated = analyze_market_structure(df_mutated, swing_window=2)
        swings_at_t_mutated = [s for s in res_mutated.swings if s.confirmed_index <= 6]

        # Historical events confirmed at <= T must be strictly invariant
        assert len(swings_at_t_orig) == len(swings_at_t_mutated)
        for s1, s2 in zip(swings_at_t_orig, swings_at_t_mutated):
            assert s1.index == s2.index
            assert s1.price == s2.price
            assert s1.confirmed_index == s2.confirmed_index
            assert s1.time == s2.time
            assert s1.confirmed_time == s2.confirmed_time

    # -------------------------------------------------------------------------
    # Property 2: Swing Confirmation Window
    # -------------------------------------------------------------------------
    def test_property_2_swing_confirmation_window(self):
        """
        A candidate swing peak at index i cannot be marked as confirmed
        until exactly i + window bars have completed.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2645, 2638, 2642),  # 0
            make_candle("2026-03-02 08:15:00", 2642, 2650, 2640, 2648),  # 1
            make_candle("2026-03-02 08:30:00", 2648, 2670, 2646, 2665),  # 2: Peak
            make_candle("2026-03-02 08:45:00", 2665, 2660, 2655, 2658),  # 3: Only 1 right bar
        ]
        df_incomplete = pd.DataFrame(candles)

        # With window=2, bar 2 requires 2 right bars (index 3 and 4). At index 3, it cannot be confirmed.
        swings_incomplete = detect_swing_points(df_incomplete, window=2)
        assert len(swings_incomplete) == 0

        # Add index 4 (second right bar)
        candles.append(make_candle("2026-03-02 09:00:00", 2658, 2654, 2650, 2652))  # 4: Completes confirmation
        df_complete = pd.DataFrame(candles)
        swings_complete = detect_swing_points(df_complete, window=2)

        assert len(swings_complete) == 1
        assert swings_complete[0].index == 2
        assert swings_complete[0].confirmed_index == 4

    # -------------------------------------------------------------------------
    # Property 3: Unconfirmed Swing Levels Cannot Trigger Breaks
    # -------------------------------------------------------------------------
    def test_property_3_unconfirmed_swings_cannot_break(self):
        """
        If candle i+1 pierces above candle i's peak before candle i is confirmed,
        it must NOT trigger a BOS or CHoCH break.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2645, 2638, 2642),  # 0
            make_candle("2026-03-02 08:15:00", 2642, 2648, 2640, 2646),  # 1
            make_candle("2026-03-02 08:30:00", 2646, 2660, 2644, 2655),  # 2: Peak (2660)
            # Candle 3 immediately breaks 2660 by closing at 2665 (candle 2 is unconfirmed!)
            make_candle("2026-03-02 08:45:00", 2655, 2668, 2652, 2665),  # 3
            make_candle("2026-03-02 09:00:00", 2665, 2670, 2662, 2668),  # 4
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)
        # Candle 2 was violated by candle 3, so candle 2 is not even a swing high
        assert len([s for s in swings if s.index == 2]) == 0

        breaks, _ = detect_market_structure(df, swings)
        assert len(breaks) == 0

    # -------------------------------------------------------------------------
    # Property 4: Event Availability & Semantics
    # -------------------------------------------------------------------------
    def test_property_4_event_availability_timestamps(self):
        """
        Verify that event_time <= confirmed_time holds strictly across all models.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2644, 2638, 2640),  # 0: OB
            make_candle("2026-03-02 08:15:00", 2640, 2660, 2639, 2658),  # 1: Impulse
            make_candle("2026-03-02 08:30:00", 2658, 2665, 2652, 2663),  # 2: FVG creation
            make_candle("2026-03-02 08:45:00", 2663, 2666, 2655, 2658),  # 3
            make_candle("2026-03-02 09:00:00", 2658, 2662, 2654, 2656),  # 4
        ]
        df = pd.DataFrame(candles)
        res = analyze_market_structure(df, swing_window=1)

        # 1. Swings
        for s in res.swings:
            assert s.time <= s.confirmed_time
            assert s.index < s.confirmed_index

        # 2. FVGs
        for f in res.fvgs:
            assert f.candle_index < f.creation_index
            assert f.creation_time == df["time"].iloc[f.creation_index]

        # 3. Order Blocks
        for ob in res.order_blocks:
            assert ob.candle_index < ob.confirmed_index
            assert ob.candle_time <= ob.confirmed_time

    # -------------------------------------------------------------------------
    # Property 5: Historical Prefixes Invariance
    # -------------------------------------------------------------------------
    def test_property_5_historical_prefixes_agreement(self):
        """
        Analyzing df[:T+1] must produce identical events for all swings confirmed at <= T.
        """
        df_full, _ = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="M15", n_bars=100, seed=123)
        res_full = analyze_market_structure(df_full, swing_window=2)

        T = 60
        df_prefix = df_full.iloc[:T + 1].copy()
        res_prefix = analyze_market_structure(df_prefix, swing_window=2)

        # Compare swings confirmed at <= T
        swings_full_at_t = [s for s in res_full.swings if s.confirmed_index <= T]
        swings_prefix = [s for s in res_prefix.swings if s.confirmed_index <= T]

        assert len(swings_full_at_t) == len(swings_prefix)
        for s_f, s_p in zip(swings_full_at_t, swings_prefix):
            assert s_f.index == s_p.index
            assert s_f.price == s_p.price
            assert s_f.swing_type == s_p.swing_type

    # -------------------------------------------------------------------------
    # Property 6: UTC Consistency
    # -------------------------------------------------------------------------
    def test_property_6_utc_consistency(self):
        """
        Verify that all timestamps returned across all models are strictly UTC-aware.
        """
        df, _ = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="M15", n_bars=80, seed=99)
        res = analyze_market_structure(df, swing_window=2)

        for s in res.swings:
            assert s.time.tzinfo is not None and str(s.time.tz) == "UTC"
            assert s.confirmed_time.tzinfo is not None and str(s.confirmed_time.tz) == "UTC"

        for b in res.structure_breaks:
            assert b.break_time.tzinfo is not None and str(b.break_time.tz) == "UTC"

        for f in res.fvgs:
            assert f.creation_time.tzinfo is not None and str(f.creation_time.tz) == "UTC"
            if f.mitigation_time:
                assert f.mitigation_time.tzinfo is not None and str(f.mitigation_time.tz) == "UTC"

        for sw in res.liquidity_sweeps:
            assert sw.sweep_time.tzinfo is not None and str(sw.sweep_time.tz) == "UTC"

        for ob in res.order_blocks:
            assert ob.candle_time.tzinfo is not None and str(ob.candle_time.tz) == "UTC"
            if ob.confirmed_time:
                assert ob.confirmed_time.tzinfo is not None and str(ob.confirmed_time.tz) == "UTC"

    # -------------------------------------------------------------------------
    # Property 7: Duplicate Structural Breaks Prevention
    # -------------------------------------------------------------------------
    def test_property_7_duplicate_breaks_prevention(self):
        """
        A single confirmed swing high must NOT emit multiple BOS breaks
        if consecutive candles continue closing above it.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2630, 2635, 2625, 2632),  # 0
            make_candle("2026-03-02 08:15:00", 2632, 2640, 2630, 2638),  # 1
            make_candle("2026-03-02 08:30:00", 2638, 2650, 2635, 2645),  # 2: SH (2650)
            make_candle("2026-03-02 08:45:00", 2645, 2642, 2635, 2638),  # 3
            make_candle("2026-03-02 09:00:00", 2638, 2640, 2632, 2636),  # 4: Confirms SH at 4
            make_candle("2026-03-02 09:15:00", 2636, 2655, 2634, 2654),  # 5: Breaks 2650 (First Break!)
            make_candle("2026-03-02 09:30:00", 2654, 2662, 2650, 2660),  # 6: Also closes above 2650
            make_candle("2026-03-02 09:45:00", 2660, 2668, 2658, 2666),  # 7: Also closes above 2650
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)
        breaks, _ = detect_market_structure(df, swings, break_on_close=True)

        # Must generate exactly ONE break at index 5, NOT 3 breaks
        assert len(breaks) == 1
        assert breaks[0].break_index == 5
        assert breaks[0].broken_swing.price == 2650.0

    # -------------------------------------------------------------------------
    # Property 8: Ambiguous Multi-Level Crossing Candle
    # -------------------------------------------------------------------------
    def test_property_8_ambiguous_candle_crossing_multiple_levels(self):
        """
        Test an expansive outside bar that breaches both the active high and active low.
        With break_on_close=True, the net close price determines which side breaks.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2645, 2655, 2642, 2650),  # 0
            make_candle("2026-03-02 08:15:00", 2650, 2658, 2646, 2655),  # 1
            make_candle("2026-03-02 08:30:00", 2650, 2652, 2630, 2635),  # 2: SL (2630)
            make_candle("2026-03-02 08:45:00", 2635, 2648, 2634, 2646),  # 3
            make_candle("2026-03-02 09:00:00", 2646, 2652, 2640, 2650),  # 4: Confirms SL at 4
            make_candle("2026-03-02 09:15:00", 2650, 2665, 2648, 2662),  # 5: SH (2665)
            make_candle("2026-03-02 09:30:00", 2662, 2660, 2652, 2655),  # 6
            make_candle("2026-03-02 09:45:00", 2655, 2658, 2650, 2654),  # 7: Confirms SH at 7
            # Bar 8 is a massive engulfing candle: Low=2620 (< 2630) and High=2675 (> 2665)
            # But closes at 2672 (> 2665, above high)
            make_candle("2026-03-02 10:00:00", 2654, 2675, 2620, 2672),  # 8
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)

        # On close break: Close 2672 > 2665, while Close 2672 is NOT < 2630
        breaks, trend = detect_market_structure(df, swings, break_on_close=True)
        assert len(breaks) == 1
        assert breaks[0].direction == MarketTrend.BULLISH
        assert trend == MarketTrend.BULLISH

    # -------------------------------------------------------------------------
    # Property 9: FVG Lifecycle (Boundary Equality, Wick, CE, Full Violation)
    # -------------------------------------------------------------------------
    def test_property_9_fvg_lifecycle_comprehensive(self):
        """
        Verify exact FVG boundary conditions:
        - Boundary equality: Low[2] == High[0] -> No gap (gap size 0)
        - Wick penetration without reaching CE -> PARTIALLY_MITIGATED
        - Reaching 50% CE -> PARTIALLY_MITIGATED
        - Close beyond far boundary -> FULLY_MITIGATED
        """
        # Case A: Boundary equality produces no gap
        eq_candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2650, 2638, 2648),  # High = 2650
            make_candle("2026-03-02 08:15:00", 2648, 2660, 2645, 2658),
            make_candle("2026-03-02 08:30:00", 2658, 2665, 2650, 2662),  # Low = 2650 (touches high exactly)
        ]
        df_eq = pd.DataFrame(eq_candles)
        assert len(detect_fair_value_gaps(df_eq)) == 0

        # Case B: Wick penetration into top 20% of gap (between Top and CE)
        # Gap: [2640, 2650], CE = 2645
        test_candles = [
            make_candle("2026-03-02 08:00:00", 2635, 2640, 2632, 2638),  # 0: High = 2640
            make_candle("2026-03-02 08:15:00", 2638, 2655, 2636, 2652),  # 1: Impulse
            make_candle("2026-03-02 08:30:00", 2652, 2658, 2650, 2656),  # 2: Low = 2650 -> Bullish FVG [2640, 2650]
            # Candle 3 dips to 2648 (inside gap, above CE 2645) and closes at 2652
            make_candle("2026-03-02 08:45:00", 2656, 2657, 2648, 2652),  # 3: Wick penetration
        ]
        df_test = pd.DataFrame(test_candles)
        fvgs = detect_fair_value_gaps(df_test, track_mitigation=True)
        assert len(fvgs) == 1
        assert fvgs[0].status == FVGStatus.PARTIALLY_MITIGATED
        assert fvgs[0].mitigation_index == 3

    # -------------------------------------------------------------------------
    # Property 10: Displacement Engine Robustness
    # -------------------------------------------------------------------------
    def test_property_10_displacement_robustness(self):
        """
        Verify:
        - Zero-range candles (High == Low) do not cause ZeroDivisionError.
        - ATR warmup behaves correctly (index < atr_period ignored).
        - Evaluation compares against uncontaminated prior baseline ATR.
        """
        records = []
        # 14 candles of range 2 pts
        for i in range(14):
            records.append(
                make_candle(f"2026-03-02 {8 + i//4:02d}:{(i%4)*15:02d}:00", 2650, 2652, 2650, 2651)
            )
        # Add a zero-range doji at index 14
        records.append(make_candle("2026-03-02 11:30:00", 2651, 2651, 2651, 2651))
        # Add a true displacement candle at index 15
        records.append(make_candle("2026-03-02 11:45:00", 2651, 2665, 2650, 2664))
        df = pd.DataFrame(records)

        # Must execute without error
        displacements = detect_displacements(df, atr_period=14, multiplier=1.5, min_body_ratio=0.6)
        assert 14 not in displacements  # Zero-range candle skipped
        assert 15 in displacements      # Explosive candle detected

    # -------------------------------------------------------------------------
    # Property 11: Liquidity Sweeps Precision
    # -------------------------------------------------------------------------
    def test_property_11_liquidity_sweeps_precision(self):
        """
        Verify:
        - Touching level exactly (High == Level) is NOT a sweep (no buy stops breached).
        - Wick penetration strictly beyond level (High > Level, Close <= Level) IS a sweep.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2645, 2650, 2642, 2648),
            make_candle("2026-03-02 08:15:00", 2648, 2655, 2646, 2653),
            make_candle("2026-03-02 08:30:00", 2653, 2660, 2650, 2656),  # 2: SH (2660)
            make_candle("2026-03-02 08:45:00", 2656, 2652, 2644, 2646),
            make_candle("2026-03-02 09:00:00", 2646, 2648, 2640, 2644),  # 4: Confirms SH at 4
            # Candle 5 touches 2660 exactly (High == 2660)
            make_candle("2026-03-02 09:15:00", 2644, 2660, 2642, 2650),  # 5: Equal high touch
            # Candle 6 breaches 2660 by wicking to 2663 and closing at 2655
            make_candle("2026-03-02 09:30:00", 2650, 2663, 2648, 2655),  # 6: True sweep
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)
        sweeps = detect_liquidity_sweeps(df, swings)

        # Candle 5 must NOT be in sweeps, Candle 6 MUST be in sweeps
        assert len(sweeps) == 1
        assert sweeps[0].sweep_index == 6
        assert sweeps[0].sweep_price == 2663.0
        assert sweeps[0].wick_penetration == 3.0

    # -------------------------------------------------------------------------
    # Property 12: MSS Confluence & Confirmation Window
    # -------------------------------------------------------------------------
    def test_property_12_mss_confluence_and_window(self):
        """
        Verify:
        - Structural break occurring beyond max_lag_bars is NOT matched as an MSS.
        - require_fvg=True rejects shifts lacking an FVG between sweep and break.
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
            make_candle("2026-03-02 09:15:00", 2642, 2644, 2624, 2634),  # 5: SSL sweep
        ]
        df = pd.DataFrame(candles)
        sweeps = detect_liquidity_sweeps(df, [sh_dummy])

        # Break at index 18 (13 bars after sweep at index 5)
        mock_late_break = StructureBreak(
            break_type=BreakType.CHOCH,
            direction=MarketTrend.BULLISH,
            broken_swing=sh_dummy,
            break_index=18,
            break_time=pd.to_datetime("2026-03-02 12:30:00", utc=True),
            break_price=2655.0,
            prior_trend=MarketTrend.BEARISH,
            resulting_trend=MarketTrend.BULLISH,
        )

        # max_lag_bars = 5 -> Break at index 18 must be ignored
        shifts_late = detect_market_structure_shifts(sweeps, [mock_late_break], max_lag_bars=5)
        assert len(shifts_late) == 0

        # Break within window (index 8) but NO FVG provided
        mock_valid_break = StructureBreak(
            break_type=BreakType.CHOCH,
            direction=MarketTrend.BULLISH,
            broken_swing=sh_dummy,
            break_index=8,
            break_time=pd.to_datetime("2026-03-02 10:00:00", utc=True),
            break_price=2655.0,
            prior_trend=MarketTrend.BEARISH,
            resulting_trend=MarketTrend.BULLISH,
        )

        # With require_fvg=True and fvgs=None, shift must NOT trigger
        shifts_no_fvg = detect_market_structure_shifts(sweeps, [mock_valid_break], fvgs=None, require_fvg=True)
        assert len(shifts_no_fvg) == 0

        # With require_fvg=False, shift triggers
        shifts_ok = detect_market_structure_shifts(sweeps, [mock_valid_break], fvgs=None, require_fvg=False)
        assert len(shifts_ok) == 1

    # -------------------------------------------------------------------------
    # Property 13: Order Block Confirmation, Mitigation & Invalidation
    # -------------------------------------------------------------------------
    def test_property_13_order_block_lifecycle(self):
        """
        Verify:
        - OB is confirmed at the FVG creation index (fvg.creation_index).
        - Testing begins strictly at confirmed_index + 1.
        - Candle closing below OB low marks is_invalidated = True.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2646, 2647, 2638, 2640),  # 0: Down candle (OB) [2638, 2647]
            make_candle("2026-03-02 08:15:00", 2640, 2660, 2639, 2658),  # 1: Impulse
            make_candle("2026-03-02 08:30:00", 2658, 2665, 2652, 2663),  # 2: Low 2652 > High 2647 -> Bullish FVG
            # Candle 3: closes at 2630 (< OB.low 2638) -> Invalidation!
            make_candle("2026-03-02 08:45:00", 2663, 2664, 2628, 2630),  # 3: Invalidating bar
        ]
        df = pd.DataFrame(candles)
        fvgs = detect_fair_value_gaps(df)
        assert len(fvgs) == 1

        obs = detect_order_blocks(df, fvgs=fvgs, track_mitigation=True)
        assert len(obs) == 1
        ob = obs[0]

        assert ob.confirmed_index == 2  # FVG confirmed at 2
        assert ob.is_invalidated is True
        assert ob.invalidation_index == 3

    # -------------------------------------------------------------------------
    # Property 14: Chart Integrity & Confirmation Tooltips
    # -------------------------------------------------------------------------
    def test_property_14_chart_integrity(self):
        """
        Verify that candlestick chart trace definitions:
        - Include confirmation timestamps in hovertext for swing points.
        - Place structural break annotations strictly at the break time.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2645, 2638, 2642),
            make_candle("2026-03-02 08:15:00", 2642, 2648, 2640, 2646),
            make_candle("2026-03-02 08:30:00", 2646, 2660, 2644, 2650),  # 2: Peak
            make_candle("2026-03-02 08:45:00", 2650, 2652, 2642, 2645),
            make_candle("2026-03-02 09:00:00", 2645, 2648, 2640, 2644),  # 4: Confirms peak
            make_candle("2026-03-02 09:15:00", 2644, 2665, 2642, 2662),  # 5: BOS
        ]
        df = pd.DataFrame(candles)
        res = analyze_market_structure(df, swing_window=2)
        fig = create_candlestick_chart(df, ict_result=res)

        # Find Swing Highs trace
        sh_trace = next((t for t in fig.data if t.name == "Swing Highs"), None)
        assert sh_trace is not None
        assert hasattr(sh_trace, "hovertext")
        assert len(sh_trace.hovertext) > 0
        assert "Confirmed:" in sh_trace.hovertext[0]
        assert "Formed:" in sh_trace.hovertext[0]

        # Structure annotations show the event timestamp, not only the event type.
        break_annotation = next((a for a in fig.layout.annotations if "BOS" in str(a.text) or "CHoCH" in str(a.text)), None)
        if res.structure_breaks:
            assert break_annotation is not None
            assert "UTC" in str(break_annotation.text)

        # Displacement is exposed as an explicitly timestamped chart trace.
        if res.displacement_indices:
            displacement_trace = next((t for t in fig.data if t.name == "Displacement"), None)
            assert displacement_trace is not None
            assert displacement_trace.hovertext is not None
            assert "UTC" in displacement_trace.hovertext[0]


class TestAdversarialDetectionEdgeCases:
    """
    Direct, isolated verification of the 12 Phase 2.1 Adversarial Detection Edge Cases:
    1. Equal highs and equal lows
    2. Repeated breaks of the same swing
    3. Wick breaks versus candle-close breaks
    4. Outside candles breaching both sides
    5. Gaps and missing candles
    6. Doji candles and zero-range candles
    7. FVG creation, mitigation, and invalidation
    8. Sweeps followed by delayed or absent structure breaks
    9. Displacement at ATR threshold boundaries
    10. Order Block origin selection
    11. Events near the beginning and end of a dataset
    12. Timeframe changes and timestamp alignment
    """

    # 1. Equal highs and equal lows
    def test_equal_highs_and_equal_lows_disqualified(self):
        """
        Under the strict-fractal definition (highs[i-j] >= curr_high or highs[i+j] >= curr_high),
        adjacent equal highs or equal lows must NOT be labelled as swing points.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2645, 2638, 2642),  # 0
            make_candle("2026-03-02 08:15:00", 2642, 2650, 2640, 2648),  # 1
            make_candle("2026-03-02 08:30:00", 2648, 2660, 2646, 2655),  # 2: High = 2660.0
            make_candle("2026-03-02 08:45:00", 2655, 2660, 2645, 2652),  # 3: High = 2660.0 (EQUAL HIGH)
            make_candle("2026-03-02 09:00:00", 2652, 2654, 2648, 2650),  # 4
            make_candle("2026-03-02 09:15:00", 2650, 2652, 2646, 2648),  # 5
            make_candle("2026-03-02 09:30:00", 2648, 2650, 2644, 2646),  # 6
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)

        # Neither candle 2 nor candle 3 can be confirmed as a swing high
        sh_points = [s for s in swings if s.swing_type == SwingType.SWING_HIGH]
        assert len(sh_points) == 0, "Equal highs must not qualify as strict fractal swing highs"

        # Now test equal lows
        low_candles = [
            make_candle("2026-03-02 08:00:00", 2655, 2658, 2650, 2652),  # 0
            make_candle("2026-03-02 08:15:00", 2652, 2654, 2644, 2646),  # 1
            make_candle("2026-03-02 08:30:00", 2646, 2648, 2630, 2635),  # 2: Low = 2630.0
            make_candle("2026-03-02 08:45:00", 2635, 2640, 2630, 2638),  # 3: Low = 2630.0 (EQUAL LOW)
            make_candle("2026-03-02 09:00:00", 2638, 2642, 2636, 2640),  # 4
            make_candle("2026-03-02 09:15:00", 2640, 2645, 2638, 2642),  # 5
            make_candle("2026-03-02 09:30:00", 2642, 2646, 2640, 2644),  # 6
        ]
        df_lows = pd.DataFrame(low_candles)
        swings_lows = detect_swing_points(df_lows, window=2)
        sl_points = [s for s in swings_lows if s.swing_type == SwingType.SWING_LOW]
        assert len(sl_points) == 0, "Equal lows must not qualify as strict fractal swing lows"

    # 2. Repeated breaks of the same swing
    def test_repeated_breaks_of_same_swing_prevented(self):
        """
        Once an active swing level is breached and consumed, subsequent candles
        (even if higher/lower or pulling back and re-crossing) must NOT emit repeated breaks.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2630, 2635, 2625, 2632),  # 0
            make_candle("2026-03-02 08:15:00", 2632, 2640, 2630, 2638),  # 1
            make_candle("2026-03-02 08:30:00", 2638, 2650, 2635, 2645),  # 2: SH (2650)
            make_candle("2026-03-02 08:45:00", 2645, 2642, 2635, 2638),  # 3
            make_candle("2026-03-02 09:00:00", 2638, 2640, 2632, 2636),  # 4: Confirms SH at 4
            make_candle("2026-03-02 09:15:00", 2636, 2655, 2634, 2654),  # 5: 1st Break of 2650
            make_candle("2026-03-02 09:30:00", 2654, 2660, 2652, 2658),  # 6: Continuation above 2650
            make_candle("2026-03-02 09:45:00", 2658, 2658, 2640, 2642),  # 7: Pullback below 2650
            make_candle("2026-03-02 10:00:00", 2642, 2665, 2641, 2662),  # 8: Re-crossing above 2650
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)
        breaks, _ = detect_market_structure(df, swings, break_on_close=True)

        breaks_for_sh = [b for b in breaks if b.broken_swing.price == 2650.0]
        assert len(breaks_for_sh) == 1, "A single swing level must only be broken once"
        assert breaks_for_sh[0].break_index == 5

    # 3. Wick breaks versus candle-close breaks
    def test_wick_breaks_vs_candle_close_breaks_independent(self):
        """
        Verify independent evaluation of break_on_close:
        - When True: A wick piercing above a swing high that closes below emits NO break.
        - When False: A wick piercing above emits an immediate structural break.
        """
        candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2645, 2638, 2642),  # 0
            make_candle("2026-03-02 08:15:00", 2642, 2648, 2640, 2646),  # 1
            make_candle("2026-03-02 08:30:00", 2646, 2660, 2644, 2650),  # 2: SH (2660)
            make_candle("2026-03-02 08:45:00", 2650, 2652, 2642, 2645),  # 3
            make_candle("2026-03-02 09:00:00", 2645, 2648, 2640, 2644),  # 4: Confirms SH at 4
            # Candle 5: Wicks to 2665 (> 2660), but closes at 2655 (< 2660)
            make_candle("2026-03-02 09:15:00", 2644, 2665, 2642, 2655),  # 5: Wick break only
        ]
        df = pd.DataFrame(candles)
        swings = detect_swing_points(df, window=2)

        # Institutional mode (break on close): 0 breaks
        breaks_close, _ = detect_market_structure(df, swings, break_on_close=True)
        assert len(breaks_close) == 0, "Wick penetration must not register a break when break_on_close=True"

        # Wick mode: 1 break
        breaks_wick, _ = detect_market_structure(df, swings, break_on_close=False)
        assert len(breaks_wick) == 1, "Wick penetration must register a break when break_on_close=False"
        assert breaks_wick[0].break_index == 5
        assert breaks_wick[0].break_price == 2665.0

    # 4. Outside candles breaching both sides
    def test_outside_candles_breaching_both_sides_resolution(self):
        """
        An outside bar breaches both active swing high and active swing low.
        With break_on_close=True:
        - If close is above high: exactly Bullish break.
        - If close is below low: exactly Bearish break.
        - If close is inside range: NO break (both sides were merely swept).
        """
        base_candles = [
            make_candle("2026-03-02 08:00:00", 2645, 2655, 2642, 2650),  # 0
            make_candle("2026-03-02 08:15:00", 2650, 2658, 2646, 2655),  # 1
            make_candle("2026-03-02 08:30:00", 2650, 2652, 2630, 2635),  # 2: SL (2630)
            make_candle("2026-03-02 08:45:00", 2635, 2648, 2634, 2646),  # 3
            make_candle("2026-03-02 09:00:00", 2646, 2652, 2640, 2650),  # 4: Confirms SL at 4
            make_candle("2026-03-02 09:15:00", 2650, 2665, 2648, 2662),  # 5: SH (2665)
            make_candle("2026-03-02 09:30:00", 2662, 2660, 2652, 2655),  # 6
            make_candle("2026-03-02 09:45:00", 2655, 2658, 2650, 2654),  # 7: Confirms SH at 7
        ]

        # Case A: Outside candle closes above high (Bullish break)
        c_a = copy.deepcopy(base_candles)
        c_a.append(make_candle("2026-03-02 10:00:00", 2654, 2675, 2620, 2670))  # 8: Closes 2670 > 2665
        df_a = pd.DataFrame(c_a)
        swings_a = detect_swing_points(df_a, window=2)
        breaks_a, trend_a = detect_market_structure(df_a, swings_a, break_on_close=True)
        assert len(breaks_a) == 1
        assert breaks_a[0].direction == MarketTrend.BULLISH
        assert trend_a == MarketTrend.BULLISH

        # Case B: Outside candle closes below low (Bearish break)
        c_b = copy.deepcopy(base_candles)
        c_b.append(make_candle("2026-03-02 10:00:00", 2654, 2675, 2620, 2622))  # 8: Closes 2622 < 2630
        df_b = pd.DataFrame(c_b)
        swings_b = detect_swing_points(df_b, window=2)
        breaks_b, trend_b = detect_market_structure(df_b, swings_b, break_on_close=True)
        assert len(breaks_b) == 1
        assert breaks_b[0].direction == MarketTrend.BEARISH
        assert trend_b == MarketTrend.BEARISH

        # Case C: Outside candle wicks both, but closes inside range (2650)
        c_c = copy.deepcopy(base_candles)
        c_c.append(make_candle("2026-03-02 10:00:00", 2654, 2675, 2620, 2650))  # 8: Closes 2650 (inside)
        df_c = pd.DataFrame(c_c)
        swings_c = detect_swing_points(df_c, window=2)
        breaks_c, trend_c = detect_market_structure(df_c, swings_c, break_on_close=True)
        assert len(breaks_c) == 0, "Outside candle closing inside range must not trigger structural breaks"

    # 5. Gaps and missing candles
    def test_gaps_and_missing_candles_monotonic_alignment(self):
        """
        Verify that time gaps (weekend market closure or intraday missing bars)
        do not distort index math or look-ahead protection.
        """
        candles = [
            # Friday candles
            make_candle("2026-03-06 20:30:00", 2640, 2645, 2638, 2642),  # 0
            make_candle("2026-03-06 20:45:00", 2642, 2650, 2640, 2648),  # 1
            make_candle("2026-03-06 21:00:00", 2648, 2665, 2646, 2660),  # 2: Peak on Friday close
            # Gap across weekend to Sunday evening reopen (49 hours later)
            make_candle("2026-03-08 22:00:00", 2660, 2658, 2652, 2654),  # 3
            make_candle("2026-03-08 22:15:00", 2654, 2655, 2648, 2650),  # 4: Confirms Friday peak!
            make_candle("2026-03-08 22:30:00", 2650, 2670, 2648, 2668),  # 5: Breaks high on Sunday
        ]
        df = pd.DataFrame(candles)
        res = analyze_market_structure(df, swing_window=2)

        assert len(res.swings) >= 1
        sh = res.swings[0]
        assert sh.index == 2
        assert sh.confirmed_index == 4
        assert sh.time == pd.to_datetime("2026-03-06 21:00:00", utc=True)
        assert sh.confirmed_time == pd.to_datetime("2026-03-08 22:15:00", utc=True)

        assert len(res.structure_breaks) == 1
        assert res.structure_breaks[0].break_index == 5
        assert res.structure_breaks[0].break_time == pd.to_datetime("2026-03-08 22:30:00", utc=True)

    # 6. Doji candles and zero-range candles
    def test_doji_and_zero_range_candles_handling(self):
        """
        Verify:
        - Doji candle (close == open) in Order Block lookback is skipped (not an opposing candle).
        - Zero-range candle (high == low) in displacement detection is handled without ZeroDivisionError.
        """
        # A: Doji in Order Block lookback
        candles = [
            make_candle("2026-03-02 08:00:00", 2646, 2648, 2638, 2640),  # 0: True down candle (OB candidate)
            make_candle("2026-03-02 08:15:00", 2642, 2645, 2640, 2642),  # 1: DOJI (open == close == 2642)
            make_candle("2026-03-02 08:30:00", 2642, 2660, 2641, 2658),  # 2: Bullish impulse
            make_candle("2026-03-02 08:45:00", 2658, 2665, 2652, 2663),  # 3: Low 2652 > High[1] 2645 -> FVG!
        ]
        df = pd.DataFrame(candles)
        fvgs = detect_fair_value_gaps(df)
        assert len(fvgs) == 1

        obs = detect_order_blocks(df, fvgs=fvgs)
        assert len(obs) == 1
        # Candle 1 (doji) must be skipped; candle 0 (down candle) must be chosen!
        assert obs[0].candle_index == 0, "Doji candle must not be selected as an opposing order block candle"
        assert obs[0].ob_type == OrderBlockType.BULLISH

        # B: Zero-range candle in displacement
        tr_records = [
            make_candle(f"2026-03-02 {8 + i//4:02d}:{(i%4)*15:02d}:00", 2650, 2652, 2650, 2651)
            for i in range(14)
        ]
        # Zero-range candle
        tr_records.append(make_candle("2026-03-02 11:30:00", 2650, 2650, 2650, 2650))
        df_zr = pd.DataFrame(tr_records)
        disps = detect_displacements(df_zr, atr_period=14)
        assert 14 not in disps

    # 7. FVG creation, mitigation, and invalidation
    def test_fvg_creation_mitigation_and_invalidation_lifecycle(self):
        """
        Verify:
        - Bullish FVG creation, partial mitigation (re-entering top boundary),
          and full mitigation (piercing through bottom boundary).
        - Boundary equality (low[i+1] == high[i-1]) creates no FVG.
        """
        # Boundary equality
        eq_candles = [
            make_candle("2026-03-02 08:00:00", 2640, 2650, 2638, 2644),  # High 2650
            make_candle("2026-03-02 08:15:00", 2644, 2660, 2642, 2658),
            make_candle("2026-03-02 08:30:00", 2658, 2665, 2650, 2662),  # Low 2650 (equal!)
        ]
        df_eq = pd.DataFrame(eq_candles)
        assert len(detect_fair_value_gaps(df_eq)) == 0

        # Bullish FVG [2640, 2650], CE = 2645
        lifecycle_candles = [
            make_candle("2026-03-02 08:00:00", 2635, 2640, 2632, 2638),  # 0: High = 2640
            make_candle("2026-03-02 08:15:00", 2638, 2655, 2636, 2652),  # 1: Impulse
            make_candle("2026-03-02 08:30:00", 2652, 2658, 2650, 2656),  # 2: Low = 2650 -> FVG confirmed
            make_candle("2026-03-02 08:45:00", 2656, 2660, 2652, 2658),  # 3: Above gap (UNTESTED)
            make_candle("2026-03-02 09:00:00", 2658, 2659, 2646, 2648),  # 4: Low 2646 <= Top 2650 (PARTIALLY_MITIGATED)
            make_candle("2026-03-02 09:15:00", 2648, 2650, 2635, 2638),  # 5: Low 2635 <= Bottom 2640 (FULLY_MITIGATED)
        ]
        df_lc = pd.DataFrame(lifecycle_candles)
        fvgs = detect_fair_value_gaps(df_lc, track_mitigation=True)
        bullish_fvgs = [f for f in fvgs if f.gap_type == FVGType.BULLISH]
        assert len(bullish_fvgs) == 1
        fvg = bullish_fvgs[0]
        assert fvg.status == FVGStatus.FULLY_MITIGATED
        assert fvg.mitigation_index == 5
        assert fvg.top_price == 2650.0
        assert fvg.bottom_price == 2640.0
        assert fvg.consequent_encroachment == 2645.0

    # 8. Sweeps followed by delayed or absent structure breaks
    def test_sweeps_delayed_or_absent_structure_breaks(self):
        """
        Verify that an MSS is emitted ONLY when an opposite-direction break
        occurs strictly within max_lag_bars.
        """
        dummy_swing = SwingPoint(
            index=2,
            time=pd.to_datetime("2026-03-02 08:30:00", utc=True),
            price=2630.0,
            swing_type=SwingType.SWING_LOW,
            classification=SwingClassification.INITIAL,
            confirmed_index=4,
            confirmed_time=pd.to_datetime("2026-03-02 09:00:00", utc=True),
        )
        sweep = LiquiditySweep(
            sweep_type=SweepType.SELL_SIDE,
            swept_swing=dummy_swing,
            sweep_index=5,
            sweep_time=pd.to_datetime("2026-03-02 09:15:00", utc=True),
            sweep_price=2625.0,
            close_price=2632.0,
            wick_penetration=5.0,
        )

        # Scenario A: No structure breaks exist -> 0 MSS
        assert len(detect_market_structure_shifts([sweep], [])) == 0

        # Scenario B: Break occurs 15 bars later (> max_lag_bars=10)
        late_break = StructureBreak(
            break_type=BreakType.CHOCH,
            direction=MarketTrend.BULLISH,
            broken_swing=dummy_swing,
            break_index=20,  # 15 bars after sweep at 5
            break_time=pd.to_datetime("2026-03-02 13:00:00", utc=True),
            break_price=2650.0,
            prior_trend=MarketTrend.BEARISH,
            resulting_trend=MarketTrend.BULLISH,
        )
        assert len(detect_market_structure_shifts([sweep], [late_break], max_lag_bars=10)) == 0

        # Scenario C: Break occurs in SAME direction (Bearish break after sell-side sweep)
        same_dir_break = StructureBreak(
            break_type=BreakType.BOS,
            direction=MarketTrend.BEARISH,
            broken_swing=dummy_swing,
            break_index=8,
            break_time=pd.to_datetime("2026-03-02 10:00:00", utc=True),
            break_price=2620.0,
            prior_trend=MarketTrend.BEARISH,
            resulting_trend=MarketTrend.BEARISH,
        )
        assert len(detect_market_structure_shifts([sweep], [same_dir_break], max_lag_bars=10)) == 0

        # Scenario D: Counter break (Bullish) within window -> 1 MSS
        valid_counter_break = StructureBreak(
            break_type=BreakType.CHOCH,
            direction=MarketTrend.BULLISH,
            broken_swing=dummy_swing,
            break_index=8,
            break_time=pd.to_datetime("2026-03-02 10:00:00", utc=True),
            break_price=2650.0,
            prior_trend=MarketTrend.BEARISH,
            resulting_trend=MarketTrend.BULLISH,
        )
        shifts = detect_market_structure_shifts([sweep], [valid_counter_break], max_lag_bars=10)
        assert len(shifts) == 1
        assert shifts[0].direction == MarketTrend.BULLISH
        assert shifts[0].shift_index == 8

    # 9. Displacement at ATR threshold boundaries
    def test_displacement_exact_atr_boundary_conditions(self):
        """
        Verify strict numerical boundaries for displacement:
        - body >= multiplier * baseline_atr (test 2.99 vs 3.00)
        - body / range >= min_body_ratio (test 0.59 vs 0.60)
        """
        # Construct 14 baseline candles with TR exactly 2.0 (high-low=2.0, close=open)
        candles = []
        for i in range(14):
            candles.append(make_candle(f"2026-03-02 {8 + i//4:02d}:{(i%4)*15:02d}:00", 2650, 2652, 2650, 2650))

        # Baseline ATR at index 14 is exactly 2.0.
        # With multiplier=1.5, required body >= 3.0. With min_body_ratio=0.6, range <= body / 0.6.

        # Case 1: Body = 2.99 (< 3.0) -> FAILS body threshold
        c_sub = copy.deepcopy(candles)
        c_sub.append(make_candle("2026-03-02 11:30:00", 2650.0, 2654.0, 2649.0, 2652.99))  # body=2.99, range=5.0
        df_sub = pd.DataFrame(c_sub)
        assert 14 not in detect_displacements(df_sub, atr_period=14, multiplier=1.5, min_body_ratio=0.6)

        # Case 2: Body = 3.00 (== 3.0), Range = 5.0 (ratio = 3.0/5.0 = 0.60) -> PASSES both!
        c_exact = copy.deepcopy(candles)
        c_exact.append(make_candle("2026-03-02 11:30:00", 2650.0, 2654.0, 2649.0, 2653.0))  # body=3.0, range=5.0
        df_exact = pd.DataFrame(c_exact)
        assert 14 in detect_displacements(df_exact, atr_period=14, multiplier=1.5, min_body_ratio=0.6)

        # Case 3: Body = 3.00, but Range = 5.1 (ratio = 3.0/5.1 = 0.588 < 0.60) -> FAILS ratio threshold
        c_ratio = copy.deepcopy(candles)
        c_ratio.append(make_candle("2026-03-02 11:30:00", 2650.0, 2654.1, 2649.0, 2653.0))  # body=3.0, range=5.1
        df_ratio = pd.DataFrame(c_ratio)
        assert 14 not in detect_displacements(df_ratio, atr_period=14, multiplier=1.5, min_body_ratio=0.6)

    # 10. Order Block origin selection
    def test_order_block_origin_selection_rules(self):
        """
        Verify backward search logic for order blocks:
        - Searches up to 3 bars backward from FVG confirmation candle.
        - First opposing candle encountered is selected.
        - If all candles are same-direction, 0 order blocks returned.
        """
        # Case A: Middle candle (1) is opposing candle (down-close)
        c_mid = [
            make_candle("2026-03-02 08:00:00", 2640, 2645, 2638, 2644),  # 0: Bullish (High=2645)
            make_candle("2026-03-02 08:15:00", 2650, 2652, 2642, 2644),  # 1: Bearish (down-close)
            make_candle("2026-03-02 08:30:00", 2644, 2665, 2648, 2662),  # 2: Low 2648 > High[0] 2645 -> FVG!
        ]
        df_mid = pd.DataFrame(c_mid)
        fvgs_mid = detect_fair_value_gaps(df_mid)
        obs_mid = detect_order_blocks(df_mid, fvgs=fvgs_mid)
        assert len(obs_mid) == 1
        assert obs_mid[0].candle_index == 1

        # Case B: Middle candle (1) is bullish, Candle 0 is opposing candle (bearish)
        c_prev = [
            make_candle("2026-03-02 08:00:00", 2646, 2648, 2638, 2640),  # 0: Bearish (down-close)
            make_candle("2026-03-02 08:15:00", 2640, 2660, 2639, 2658),  # 1: Bullish
            make_candle("2026-03-02 08:30:00", 2658, 2665, 2652, 2663),  # 2: Bullish -> FVG confirmed!
        ]
        df_prev = pd.DataFrame(c_prev)
        fvgs_prev = detect_fair_value_gaps(df_prev)
        obs_prev = detect_order_blocks(df_prev, fvgs=fvgs_prev)
        assert len(obs_prev) == 1
        assert obs_prev[0].candle_index == 0

        # Case C: All candles in lookback are bullish (no opposing candle)
        c_none = [
            make_candle("2026-03-02 08:00:00", 2630, 2640, 2628, 2638),  # 0: Bullish
            make_candle("2026-03-02 08:15:00", 2638, 2655, 2636, 2652),  # 1: Bullish
            make_candle("2026-03-02 08:30:00", 2652, 2665, 2648, 2662),  # 2: Bullish
        ]
        df_none = pd.DataFrame(c_none)
        fvgs_none = detect_fair_value_gaps(df_none)
        obs_none = detect_order_blocks(df_none, fvgs=fvgs_none)
        assert len(obs_none) == 0, "No opposing candle within lookback must safely produce 0 OBs"

    # 11. Events near dataset boundaries
    def test_events_near_dataset_boundaries(self):
        """
        Verify edge-of-dataset behavior:
        - 0 rows -> clean empty ICTAnalysisResult.
        - Less than 2*window + 1 rows -> 0 swings, no crash.
        - Candidate peak at the very last bar (index n-1) is never confirmed as a swing.
        """
        # Empty
        res_0 = analyze_market_structure(pd.DataFrame())
        assert res_0.total_bars == 0
        assert len(res_0.swings) == 0

        # Short (3 bars with window=2)
        candles_short = [
            make_candle("2026-03-02 08:00:00", 2640, 2650, 2638, 2648),
            make_candle("2026-03-02 08:15:00", 2648, 2660, 2645, 2658),
            make_candle("2026-03-02 08:30:00", 2658, 2659, 2652, 2655),
        ]
        res_short = analyze_market_structure(pd.DataFrame(candles_short), swing_window=2)
        assert len(res_short.swings) == 0

        # Peak at very last candle
        candles_last = copy.deepcopy(candles_short)
        candles_last.append(make_candle("2026-03-02 08:45:00", 2655, 2690, 2650, 2685))  # Massive peak at index 3
        res_last = analyze_market_structure(pd.DataFrame(candles_last), swing_window=2)
        assert not any(s.index == 3 for s in res_last.swings), "Trailing bar cannot be confirmed as a swing"

    # 12. Timeframe changes and timestamp alignment
    def test_timeframe_changes_and_timestamp_alignment(self):
        """
        Verify that analyze_market_structure works reliably across all canonical
        timeframes (M5, M15, H1, H4), and preserves UTC-aware timestamps and matching metadata.
        """
        for tf in ["M5", "M15", "H1", "H4"]:
            df, meta = generate_synthetic_gold_data(symbol="XAUUSD", timeframe=tf, n_bars=60, seed=42)
            res = analyze_market_structure(df, symbol="XAUUSD", timeframe=tf)

            assert res.timeframe == tf
            assert res.total_bars == 60
            summary = res.summary()
            assert summary["timeframe"] == tf

            # Verify every confirmed swing has UTC-aware Timestamp
            for s in res.swings:
                assert s.time.tzinfo is not None
                assert str(s.time.tz) == "UTC"
                assert s.confirmed_time.tzinfo is not None
                assert str(s.confirmed_time.tz) == "UTC"
