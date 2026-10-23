"""Tests for the pure-SMC setup hypothesis; these are not profitability tests."""
from __future__ import annotations

import pandas as pd
import pytest

from src.smc.models import (
    SMCAnalysisResult,
    SMCDirection,
    SMCLiquidityPool,
    SMCLiquiditySweep,
    SMCLiquidityType,
    SMCOrderBlock,
    SMCOrderBlockStatus,
    SMCStructureBreak,
    SMCStructureType,
    SMCSwingPoint,
    SMCSwingType,
)
from src.strategy.smc_setups import SMCSetupConfig, detect_smc_setup_candidates


def setup_fixture():
    times = pd.date_range("2026-02-02T10:00:00Z", periods=8, freq="5min")
    df = pd.DataFrame({
        "time": times,
        "open":  [104, 102, 99, 102, 103, 101.5, 102, 103],
        "high":  [106, 104, 103, 104, 107, 104, 105, 106],
        "low":   [102, 100, 98, 100, 102, 101, 101, 102],
        "close": [104, 101, 100, 101, 106, 102.5, 104, 105],
    })
    sell_pool = SMCLiquidityPool(
        SMCLiquidityType.SELL_SIDE, 99.0, 0, 1, times[0], times[1], 1, times[1], 0.1
    )
    sweep = SMCLiquiditySweep(sell_pool, 2, times[2], 98.0, 100.0, 1.0)
    broken_swing = SMCSwingPoint(1, times[1], 104.0, SMCSwingType.SWING_HIGH, "LH", 2, times[2])
    choch = SMCStructureBreak(
        SMCStructureType.CHOCH, SMCDirection.BULLISH, broken_swing,
        4, times[4], 106.0, SMCDirection.BEARISH, SMCDirection.BULLISH,
    )
    ob = SMCOrderBlock(
        SMCDirection.BULLISH, 3, times[3], 102.0, 100.0, 102.0, 101.0,
        4, times[4], SMCStructureType.CHOCH, SMCOrderBlockStatus.MITIGATED,
        mitigation_index=5, mitigation_time=times[5],
    )
    analysis = SMCAnalysisResult(
        symbol="XAUUSD", timeframe="M5", total_bars=len(df),
        current_trend=SMCDirection.BULLISH,
        swings=[broken_swing], structure_breaks=[choch],
        liquidity_pools=[sell_pool], liquidity_sweeps=[sweep], order_blocks=[ob],
    )
    return df, analysis


def test_long_setup_requires_sweep_then_choch_then_order_block_rejection():
    df, analysis = setup_fixture()
    setups = detect_smc_setup_candidates(df, analysis, SMCSetupConfig(stop_buffer=0.5, fixed_rr=2.0))
    assert len(setups) == 1
    setup = setups[0]
    assert setup.direction == SMCDirection.BULLISH
    assert setup.sweep_index == 2
    assert setup.choch_index == 4
    assert setup.signal_index == 5
    assert setup.entry_reference_price == pytest.approx(102.5)
    assert setup.stop_loss_reference == pytest.approx(97.5)
    assert setup.take_profit_reference == pytest.approx(112.5)
    assert setup.target_source == "fixed_rr_fallback"
    assert setup.reward_risk_ratio == pytest.approx(2.0)


def test_retest_signal_is_within_the_configured_post_choch_window():
    df, analysis = setup_fixture()
    # The only valid rejection is candle 5; shortening the retest horizon so
    # there is no post-break bar must suppress the setup.
    setups = detect_smc_setup_candidates(
        df, analysis, SMCSetupConfig(max_bars_choch_to_retest=1, stop_buffer=0.5)
    )
    assert len(setups) == 1
    assert setups[0].signal_index == 5


def test_premium_discount_filter_uses_only_confirmed_prior_swings():
    df, analysis = setup_fixture()
    cfg = SMCSetupConfig(require_premium_discount=True)
    # Only one swing is available in the fixture, so no equilibrium can be
    # formed as of the signal and the optional filter conservatively rejects.
    assert detect_smc_setup_candidates(df, analysis, cfg) == []


def test_invalid_strategy_parameters_are_rejected():
    with pytest.raises(ValueError):
        SMCSetupConfig(max_sweep_to_choch_bars=0)
    with pytest.raises(ValueError):
        SMCSetupConfig(fixed_rr=0)
    with pytest.raises(ValueError):
        SMCSetupConfig(minimum_reward_risk=-1)


def test_candidate_output_contains_no_execution_state():
    df, analysis = setup_fixture()
    setup = detect_smc_setup_candidates(df, analysis)[0]
    assert not hasattr(setup, "order_id")
    assert not hasattr(setup, "filled")
    assert setup.signal_time == df.loc[setup.signal_index, "time"]


def test_available_opposing_liquidity_is_preferred_over_fallback_target():
    df, analysis = setup_fixture()
    target_pool = SMCLiquidityPool(
        SMCLiquidityType.BUY_SIDE, 110.0, 0, 1, df.time.iloc[0], df.time.iloc[1], 3, df.time.iloc[3], 0.1
    )
    analysis.liquidity_pools.append(target_pool)
    setup = detect_smc_setup_candidates(df, analysis)[0]
    assert setup.take_profit_reference == pytest.approx(110.0)
    assert setup.target_source == "opposing_liquidity"
    assert setup.reward_risk_ratio == pytest.approx(1.5)


def test_no_setup_when_sweep_is_too_old_for_the_choch():
    df, analysis = setup_fixture()
    setups = detect_smc_setup_candidates(
        df, analysis, SMCSetupConfig(max_sweep_to_choch_bars=1)
    )
    assert setups == []


def test_candidate_is_rejected_when_opposing_liquidity_target_is_below_minimum_rr():
    df, analysis = setup_fixture()
    too_close = SMCLiquidityPool(
        SMCLiquidityType.BUY_SIDE, 103.0, 0, 1, df.time.iloc[0], df.time.iloc[1], 3, df.time.iloc[3], 0.1
    )
    analysis.liquidity_pools.append(too_close)
    # The level is only $0.50 above the $102.50 close against $5 of risk.
    assert detect_smc_setup_candidates(df, analysis, SMCSetupConfig(minimum_reward_risk=1.0)) == []
