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
    SMCLiquidityPool,
    SMCLiquidityType,
    SMCOrderBlockStatus,
    SMCStructureBreak,
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
    """SMC engine must never depend on the ICT engine.

    The original guard barred any mention of "FairValueGap" because FVG was
    an ICT-only concept at the time. SMC now has its own SMCFairValueGap model
    (independent from the ICT FairValueGap). The guard is updated to check
    that the SMC engine does not import from the ICT namespace while still
    allowing the SMC-specific names.
    """
    import inspect
    import src.smc.engine as smc_engine

    source = inspect.getsource(smc_engine)
    # The SMC engine must never import from the ICT subsystem.
    assert "src.ict" not in source, "SMC engine must not import from src.ict"
    # The SMC engine must not reference the ICT-specific FairValueGap class
    # (from src.ict.models). SMCFairValueGap is acceptable — check specifically.
    assert "from src.ict" not in source, "SMC engine must not import from src.ict"
    # Confirm no unqualified reference to the ICT FVG class (not SMC-prefixed).
    import re
    ict_fvg_pattern = re.compile(r'\bFairValueGap\b(?!\s*=)')  # bare FairValueGap
    non_smc_fvg = [m.group() for m in ict_fvg_pattern.finditer(source)
                   if not source[max(0, m.start() - 3):m.start()].endswith("SMC")]
    assert not non_smc_fvg, (
        f"SMC engine references non-SMC FairValueGap names: {non_smc_fvg}. "
        "Use SMCFairValueGap instead."
    )


def test_chunked_sweep_scan_finds_first_later_chunk_and_ignores_pool_creation_bar():
    n = 1100
    times = pd.date_range("2026-01-05T00:00:00Z", periods=n, freq="5min")
    opens = [10.0] * n
    highs = [10.8] * n
    lows = [9.5] * n
    closes = [10.5] * n
    # A technically qualifying candle on the creation bar must be ignored.
    highs[0], lows[0], closes[0] = 11.0, 9.0, 9.5
    # The first actionable sweep is beyond the first 512-row scan chunk.
    highs[520], lows[520], closes[520] = 11.0, 9.0, 9.5
    df = pd.DataFrame({"time": times, "open": opens, "high": highs, "low": lows, "close": closes})
    pool = SMCLiquidityPool(
        liquidity_type=SMCLiquidityType.BUY_SIDE,
        level=10.0,
        first_swing_index=0,
        second_swing_index=1,
        first_swing_time=times[0],
        second_swing_time=times[1],
        created_index=0,
        created_time=times[0],
        tolerance=0.1,
    )

    sweeps = detect_smc_liquidity_sweeps(df, [pool], min_penetration=0.5)

    assert len(sweeps) == 1
    assert sweeps[0].sweep_index == 520
    assert sweeps[0].penetration == pytest.approx(1.0)


def test_chunked_order_block_lifecycle_preserves_invalidation_precedence_after_chunk_boundary():
    n = 1100
    times = pd.date_range("2026-01-05T00:00:00Z", periods=n, freq="5min")
    opens = [20.0] * n
    highs = [21.0] * n
    lows = [19.0] * n
    closes = [20.2] * n
    # Last opposing candle before the bullish break creates the [9, 11] zone.
    opens[1], highs[1], lows[1], closes[1] = 10.5, 11.0, 9.0, 10.0
    # Price remains away from the zone until this candle, which both overlaps
    # the lower edge and closes through it: invalidation must win over mitigation.
    opens[520], highs[520], lows[520], closes[520] = 8.5, 9.0, 7.5, 8.0
    df = pd.DataFrame({"time": times, "open": opens, "high": highs, "low": lows, "close": closes})
    prior_swing = SMCSwingPoint(0, times[0], 10.0, SMCSwingType.SWING_HIGH, "INIT", 1, times[1])
    event = SMCStructureBreak(
        break_type=SMCStructureType.INITIAL_BREAK,
        direction=SMCDirection.BULLISH,
        broken_swing=prior_swing,
        break_index=2,
        break_time=times[2],
        break_price=float(closes[2]),
        prior_trend=SMCDirection.NEUTRAL,
        resulting_trend=SMCDirection.BULLISH,
    )

    blocks = detect_smc_order_blocks(df, [event], lookback=5, track_lifecycle=True)

    assert len(blocks) == 1
    assert blocks[0].invalidation_index == 520
    assert blocks[0].mitigation_index is None
    assert blocks[0].status == SMCOrderBlockStatus.INVALIDATED


def test_indexed_pool_detector_matches_legacy_backward_scan():
    """The indexed detector must keep the old latest-unpaired pairing semantics."""
    import random

    rng = random.Random(1047)
    n = 420
    times = pd.date_range("2026-01-05T00:00:00Z", periods=n, freq="5min")
    df = pd.DataFrame({
        "time": times,
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.0] * n,
    })
    swings = []
    for index in range(3, 260):
        confirmation = index + 2
        kinds = [SMCSwingType.SWING_HIGH]
        if rng.random() < 0.74:
            kinds.append(SMCSwingType.SWING_LOW)
        for kind in kinds:
            price = round(rng.randrange(390, 431) / 4.0, 2)
            swings.append(SMCSwingPoint(
                index=index,
                time=times[index],
                price=price,
                swing_type=kind,
                classification="TEST",
                confirmed_index=confirmation,
                confirmed_time=times[confirmation],
            ))
    swings.sort(key=lambda swing: (swing.index, swing.swing_type.value))
    tolerance = 0.5

    # Reference implementation: the original quadratic backward scan, kept here
    # only as a small deterministic correctness oracle for the indexed version.
    ordered = sorted(swings, key=lambda swing: (swing.confirmed_index, swing.index))
    paired = set()
    expected = []
    from src.smc.models import SMCLiquidityPool

    for i, current in enumerate(ordered):
        if current.index in paired:
            continue
        for previous in reversed(ordered[:i]):
            if previous.index in paired or previous.swing_type != current.swing_type:
                continue
            if abs(current.price - previous.price) <= tolerance:
                created_index = max(current.confirmed_index, previous.confirmed_index)
                if created_index >= len(df):
                    continue
                kind = (
                    SMCLiquidityType.BUY_SIDE
                    if current.swing_type == SMCSwingType.SWING_HIGH
                    else SMCLiquidityType.SELL_SIDE
                )
                expected.append(SMCLiquidityPool(
                    liquidity_type=kind,
                    level=(current.price + previous.price) / 2.0,
                    first_swing_index=previous.index,
                    second_swing_index=current.index,
                    first_swing_time=previous.time,
                    second_swing_time=current.time,
                    created_index=created_index,
                    created_time=times[created_index],
                    tolerance=float(tolerance),
                ))
                paired.add(current.index)
                paired.add(previous.index)
                break
    expected.sort(key=lambda pool: (pool.created_index, pool.liquidity_type.value))

    actual = detect_smc_liquidity_pools(df, swings, tolerance=tolerance)

    def pool_signature(pool):
        return (
            pool.liquidity_type, pool.level, pool.first_swing_index,
            pool.second_swing_index, pool.first_swing_time, pool.second_swing_time,
            pool.created_index, pool.created_time, pool.tolerance,
        )

    assert [pool_signature(pool) for pool in actual] == [
        pool_signature(pool) for pool in expected
    ]


def test_detect_smc_breaker_blocks_empty():
    from src.smc.engine import detect_smc_breaker_blocks
    assert detect_smc_breaker_blocks(pd.DataFrame(), []) == []


def test_detect_smc_breaker_blocks_inversion_and_lifecycle():
    from src.smc.engine import detect_smc_breaker_blocks
    from src.smc.models import (
        SMCDirection,
        SMCOrderBlock,
        SMCOrderBlockStatus,
        SMCStructureType,
        SMCBreakerBlockType,
        SMCBreakerBlockStatus,
    )

    times = pd.date_range("2026-01-01T00:00:00Z", periods=10, freq="15min")
    # Prices:
    # bar 0: origin OB
    # bar 2: OB created
    # bar 4: OB invalidated (candle closes below OB low 95.0 at 94.0) -> Bearish Breaker created
    # bar 5: Stays below zone [95.0, 105.0] (high 94.0, low 91.0)
    # bar 6: Retest of breaker zone [95.0, 105.0] (high reaches 98.0, close 97.0) -> status TESTED
    # bar 8: Invalidation of bearish breaker (close exceeds 105.0 at 108.0) -> status INVALIDATED
    df = pd.DataFrame({
        "time": times,
        "open":  [100.0, 102.0, 105.0, 101.0, 96.0, 93.0, 95.0, 98.0, 100.0, 109.0],
        "high":  [105.0, 106.0, 108.0, 102.0, 97.0, 94.0, 98.0, 101.0, 109.0, 110.0],
        "low":   [95.0,  99.0,  103.0, 97.0,  92.0, 91.0, 94.0, 96.0,  99.0,  106.0],
        "close": [102.0, 104.0, 107.0, 98.0,  94.0, 92.0, 97.0, 99.0,  108.0, 108.0],
    })

    # Fake Bullish OB that was invalidated at bar 4
    ob = SMCOrderBlock(
        direction=SMCDirection.BULLISH,
        origin_index=0,
        origin_time=times[0],
        high=105.0,
        low=95.0,
        open=100.0,
        close=102.0,
        created_index=2,
        created_time=times[2],
        confirming_break_type=SMCStructureType.BOS,
        status=SMCOrderBlockStatus.INVALIDATED,
        invalidation_index=4,
        invalidation_time=times[4],
    )

    breakers = detect_smc_breaker_blocks(df, [ob])
    assert len(breakers) == 1
    bb = breakers[0]
    # An invalidated Bullish OB becomes a Bearish Breaker
    assert bb.breaker_type == SMCBreakerBlockType.BEARISH
    assert bb.high == 105.0
    assert bb.low == 95.0
    assert bb.created_index == 4
    assert bb.created_time == times[4]
    # By bar 6 it was retested, and by bar 8 it was invalidated (close 108 > 105)
    assert bb.status == SMCBreakerBlockStatus.INVALIDATED
    assert bb.retest_index == 6
    assert bb.invalidation_index == 8


def test_analyze_smc_breaker_blocks_integration():
    from src.smc.engine import analyze_smc, SMCConfig
    from src.smc.models import SMCBreakerBlockStatus

    # A sequence that forms a swing, break, OB, then invalidates it
    n = 30
    times = pd.date_range("2026-01-01T00:00:00Z", periods=n, freq="15min")
    df = pd.DataFrame({
        "time": times,
        "open":  [100.0 + i for i in range(n)],
        "high":  [102.0 + i for i in range(n)],
        "low":   [98.0 + i for i in range(n)],
        "close": [101.0 + i for i in range(n)],
    })
    res = analyze_smc(df, config=SMCConfig(track_breaker_blocks=True))
    assert hasattr(res, "breaker_blocks")
    assert hasattr(res, "active_breaker_blocks")
    summary = res.summary()
    assert "breaker_blocks" in summary
    assert "active_breaker_blocks" in summary


def test_create_candlestick_chart_renders_smc_breaker_blocks():
    from src.visualization.charts import create_candlestick_chart
    from src.smc.models import (
        SMCAnalysisResult,
        SMCBreakerBlock,
        SMCBreakerBlockType,
        SMCBreakerBlockStatus,
        SMCOrderBlock,
        SMCDirection,
        SMCStructureType,
    )
    times = pd.date_range("2026-01-01T00:00:00Z", periods=10, freq="15min")
    df = pd.DataFrame({
        "time": times,
        "open": [100.0] * 10,
        "high": [105.0] * 10,
        "low": [95.0] * 10,
        "close": [102.0] * 10,
    })
    ob = SMCOrderBlock(
        direction=SMCDirection.BULLISH,
        origin_index=0,
        origin_time=times[0],
        high=105.0,
        low=95.0,
        open=100.0,
        close=102.0,
        created_index=2,
        created_time=times[2],
        confirming_break_type=SMCStructureType.BOS,
        status=SMCOrderBlockStatus.INVALIDATED,
        invalidation_index=4,
        invalidation_time=times[4],
    )
    bb = SMCBreakerBlock(
        breaker_type=SMCBreakerBlockType.BEARISH,
        source_order_block=ob,
        high=105.0,
        low=95.0,
        created_index=4,
        created_time=times[4],
        status=SMCBreakerBlockStatus.ACTIVE,
    )
    smc_res = SMCAnalysisResult(
        symbol="XAUUSD",
        timeframe="M15",
        total_bars=10,
        breaker_blocks=[bb],
    )
    fig = create_candlestick_chart(df, smc_result=smc_res, show_breakers=True)
    trace_names = [trace.name for trace in fig.data if trace.name]
    assert "SMC Breaker Blocks" in trace_names
