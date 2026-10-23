"""Regression tests for the independent, close-confirmed SMC engine."""
from __future__ import annotations

import pandas as pd
import pytest

from src.smc.engine import (
    SMCConfig,
    analyze_smc,
    detect_smc_liquidity_pools,
    detect_smc_liquidity_sweeps,
    detect_smc_order_blocks,
    detect_smc_structure_breaks,
    detect_smc_swings,
)
from src.smc.models import (
    SMCDirection,
    SMCLiquidityType,
    SMCOrderBlockStatus,
    SMCStructureType,
    SMCSwingPoint,
    SMCSwingType,
)


def frame_from_hlc(highs, lows, closes, opens=None):
    opens = opens or [min(max(c, lo), hi) for c, lo, hi in zip(closes, lows, highs)]
    times = pd.date_range("2026-01-05T00:00:00Z", periods=len(highs), freq="5min")
    return pd.DataFrame({
        "time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": [100] * len(highs),
    })


def structure_fixture():
    # A confirmed high at index 1 is broken at index 3. A confirmed low at
    # index 4 is later broken down at index 7, which is a CHoCH.
    highs = [10, 12, 9, 13, 11, 10, 9, 8, 7]
    lows =  [6,  7, 5,  6,  4,  5, 5, 3, 2]
    opens = [8,  9, 7, 11,  6,  6, 5.5, 4, 2.5]
    closes= [9, 11, 6, 13,  6,  7, 6.0, 3.5, 2.2]
    return frame_from_hlc(highs, lows, closes, opens)


def test_swing_has_candidate_and_confirmation_time():
    df = frame_from_hlc(
        highs=[9, 12, 10, 9, 8],
        lows=[5, 7, 6, 4, 5],
        closes=[8, 11, 8, 5, 6],
    )
    swings = detect_smc_swings(df, window=1)
    top = next(s for s in swings if s.swing_type == SMCSwingType.SWING_HIGH)
    assert top.index == 1
    assert top.confirmed_index == 2
    assert top.confirmed_time == df.loc[2, "time"]


def test_initial_break_and_choch_are_distinguished():
    df = structure_fixture()
    swings = detect_smc_swings(df, window=1)
    events, trend = detect_smc_structure_breaks(df, swings)
    assert [event.break_index for event in events[:2]] == [3, 7]
    assert events[0].break_type == SMCStructureType.INITIAL_BREAK
    assert events[0].direction == SMCDirection.BULLISH
    assert events[1].break_type == SMCStructureType.CHOCH
    assert events[1].direction == SMCDirection.BEARISH
    assert trend == SMCDirection.BEARISH


def test_swing_confirmed_on_break_bar_cannot_be_used_on_that_bar():
    # The high at index 2 is only confirmed by index 3. A break at index 3 must
    # not use that same-bar confirmation as pre-existing information.
    df = frame_from_hlc(
        highs=[9, 10, 12, 13, 9],
        lows=[5, 6, 7, 6, 4],
        closes=[8, 9, 11, 13, 5],
    )
    swings = detect_smc_swings(df, window=1)
    events, _ = detect_smc_structure_breaks(df, swings)
    assert all(not (e.break_index == 3 and e.broken_swing.index == 2) for e in events)


def test_truncation_does_not_change_events_already_known_before_cutoff():
    df = structure_fixture()
    full = analyze_smc(df, config=SMCConfig(swing_window=1))
    cutoff = 6
    prefix = analyze_smc(df.iloc[: cutoff + 1].reset_index(drop=True), config=SMCConfig(swing_window=1))
    full_prefix = [e for e in full.structure_breaks if e.break_index <= cutoff]
    assert [(e.break_index, e.break_type, e.direction) for e in full_prefix] == [
        (e.break_index, e.break_type, e.direction) for e in prefix.structure_breaks
    ]


def test_equal_high_pool_is_confirmed_only_after_second_swing_confirmation():
    df = frame_from_hlc(
        highs=[10, 12, 9, 10, 12, 11, 13],
        lows=[7, 8, 6, 7, 8, 6, 7],
        closes=[9, 11, 7, 9, 11, 8, 9],
    )
    swings = detect_smc_swings(df, window=1)
    pools = detect_smc_liquidity_pools(df, swings, tolerance=0.1)
    highs = [p for p in pools if p.liquidity_type == SMCLiquidityType.BUY_SIDE]
    assert highs
    assert highs[0].level == pytest.approx(12.0)
    assert highs[0].created_index >= max(
        next(s.confirmed_index for s in swings if s.index == highs[0].first_swing_index),
        next(s.confirmed_index for s in swings if s.index == highs[0].second_swing_index),
    )


def test_buy_side_sweep_requires_wick_above_and_close_below_pool():
    df = frame_from_hlc(
        highs=[10, 11, 9, 11, 9, 12, 10],
        lows=[7, 8, 6, 7, 6, 8, 7],
        closes=[9, 10, 7, 10, 7, 10, 9],
    )
    pool = detect_smc_liquidity_pools(
        df,
        [SMCSwingPoint(1, df.time.iloc[1], 11.0, SMCSwingType.SWING_HIGH, "INIT", 2, df.time.iloc[2]),
         SMCSwingPoint(3, df.time.iloc[3], 11.0, SMCSwingType.SWING_HIGH, "LH", 4, df.time.iloc[4])],
        tolerance=0.0,
    )[0]
    sweeps = detect_smc_liquidity_sweeps(df, [pool])
    assert len(sweeps) == 1
    assert sweeps[0].sweep_index == 5
    assert sweeps[0].liquidity_type == SMCLiquidityType.BUY_SIDE
    assert sweeps[0].penetration == pytest.approx(1.0)


def test_order_block_origin_is_last_opposing_candle_but_known_at_break():
    df = structure_fixture()
    swings = detect_smc_swings(df, window=1)
    breaks, _ = detect_smc_structure_breaks(df, swings)
    blocks = detect_smc_order_blocks(df, breaks, lookback=5, zone_basis="wick", track_lifecycle=False)
    bullish = next(block for block in blocks if block.direction == SMCDirection.BULLISH)
    assert bullish.origin_index < bullish.created_index
    assert bullish.created_index == 3
    assert bullish.created_time == df.time.iloc[3]
    assert bullish.close < bullish.open


def test_order_block_lifecycle_marks_future_mitigation_or_invalidation():
    df = structure_fixture()
    swings = detect_smc_swings(df, window=1)
    breaks, _ = detect_smc_structure_breaks(df, swings)
    blocks = detect_smc_order_blocks(df, breaks, lookback=5, track_lifecycle=True)
    assert blocks
    assert all(block.mitigation_index is None or block.mitigation_index > block.created_index for block in blocks)
    assert all(block.invalidation_index is None or block.invalidation_index > block.created_index for block in blocks)
    assert all(block.status in set(SMCOrderBlockStatus) for block in blocks)


def test_engine_empty_input_returns_empty_result():
    result = analyze_smc(pd.DataFrame())
    assert result.total_bars == 0
    assert result.current_trend == SMCDirection.NEUTRAL
    assert result.summary()["current_zone"] == "UNAVAILABLE"


@pytest.mark.parametrize("bad", [0, -1])
def test_config_rejects_invalid_swing_window(bad):
    with pytest.raises(ValueError):
        SMCConfig(swing_window=bad)


def test_invalid_or_unsorted_timestamp_data_fails_loudly():
    df = frame_from_hlc([3, 4, 3], [1, 2, 1], [2, 3, 2])
    df.loc[[0, 1], "time"] = df.loc[[1, 0], "time"].to_numpy()
    with pytest.raises(ValueError, match="chronological"):
        analyze_smc(df)


def test_engine_does_not_require_fvg_or_displacement_inputs():
    df = structure_fixture()
    # The engine contract requires only OHLC plus time; it must not invoke ICT.
    result = analyze_smc(df, config=SMCConfig(swing_window=1))
    assert result.total_bars == len(df)
    assert hasattr(result, "liquidity_pools")
    assert not hasattr(result, "fvgs")


def test_smc_chart_overlays_are_separate_from_ict_overlays():
    from src.visualization.charts import create_candlestick_chart

    df = structure_fixture()
    result = analyze_smc(df, config=SMCConfig(swing_window=1))
    fig = create_candlestick_chart(
        df,
        smc_result=result,
        show_swings=True,
        show_structure_breaks=True,
        show_sweeps=True,
        show_order_blocks=True,
        show_liquidity_pools=True,
    )
    trace_names = [trace.name for trace in fig.data if trace.name]
    assert "Price" in trace_names
    assert "SMC Confirmed Swing Highs" in trace_names
    assert "SMC Confirmed Swing Lows" in trace_names
    assert "SMC Order Blocks" in trace_names
    # In a pure-SMC view, ICT's FVG / displacement traces are not added.
    assert "FVG Events" not in trace_names
    assert "Displacement" not in trace_names


def test_smc_rules_do_not_import_or_require_ict_engine():
    import inspect
    import src.smc.engine as smc_engine

    source = inspect.getsource(smc_engine)
    assert "src.ict" not in source
    assert "FairValueGap" not in source
