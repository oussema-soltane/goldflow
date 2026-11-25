"""Unit tests for the Higher-Timeframe Directional Bias Engine."""
from __future__ import annotations

import pandas as pd
import pytest

from src.smc.engine import SMCConfig
from src.smc.models import SMCDirection
from src.strategy.htf_bias import (
    HTFDirectionalBiasEngine,
    aggregate_daily_bars,
)
from src.strategy.smc_setups import SMCSetupCandidate


@pytest.fixture
def sample_h4_df():
    """Generates synthetic H4 bars spanning 60 days with clear trends."""
    # 60 days * 6 bars/day = 360 bars
    times = pd.date_range("2026-01-01 00:00:00", periods=360, freq="4h", tz="UTC")
    # First 30 days uptrend, next 30 days downtrend
    prices = []
    base = 2000.0
    for i in range(360):
        if i < 180:
            base += 0.5  # uptrend
        else:
            base -= 0.5  # downtrend
        prices.append(base)

    df = pd.DataFrame({
        "time": times,
        "open": [p - 0.2 for p in prices],
        "high": [p + 1.0 for p in prices],
        "low": [p - 1.0 for p in prices],
        "close": prices,
        "tick_volume": [1000] * 360,
        "spread": [0.20] * 360,
    })
    return df


def test_aggregate_daily_bars_basic(sample_h4_df):
    """Verifies that 360 H4 bars are aggregated into completed calendar days."""
    daily = aggregate_daily_bars(sample_h4_df, source_timeframe="H4")
    assert not daily.empty
    assert len(daily) == 60
    assert daily["time"].iloc[0] == pd.Timestamp("2026-01-01 00:00:00+00:00")
    # Each day starts at 00:00:00
    assert (daily["time"].dt.hour == 0).all()
    assert (daily["time"].dt.minute == 0).all()


def test_aggregate_daily_bars_drops_incomplete_trailing():
    """An incomplete final day must be dropped to prevent partial bar lookahead."""
    times = pd.date_range("2026-01-01 00:00:00", periods=8, freq="4h", tz="UTC")
    # Day 1: 6 bars (00, 04, 08, 12, 16, 20). Day 2: 2 bars (00, 04) - incomplete
    df = pd.DataFrame({
        "time": times,
        "open": 2000.0,
        "high": 2005.0,
        "low": 1995.0,
        "close": 2002.0,
        "tick_volume": 500,
    })
    daily = aggregate_daily_bars(df, source_timeframe="H4", drop_incomplete_trailing_day=True)
    assert len(daily) == 1
    assert daily["time"].iloc[0] == pd.Timestamp("2026-01-01 00:00:00+00:00")


def test_htf_directional_bias_engine_boundary_enforcement(sample_h4_df):
    """Decisions beyond confirmed HTF data end time must be rejected (fail-closed)."""
    engine = HTFDirectionalBiasEngine(sample_h4_df)
    # The last bar open is times[-1], end time is times[-1] + 4h
    h4_end = sample_h4_df["time"].max() + pd.Timedelta(hours=4)

    # Within boundary
    res_within = engine.evaluate_bias(h4_end - pd.Timedelta(minutes=5))
    assert res_within.rejection_reason != "beyond_h4_data_boundary"

    # Beyond boundary
    res_beyond = engine.evaluate_bias(h4_end + pd.Timedelta(hours=1))
    assert not res_beyond.is_aligned
    assert res_beyond.bias == SMCDirection.NEUTRAL
    assert res_beyond.rejection_reason in ("beyond_h4_data_boundary", "beyond_d1_data_boundary")


def test_htf_candidate_filtering():
    """Verify that filter_candidates accepts only aligned setups and records audit trail."""
    # Use real clean H4 dataset
    from pathlib import Path
    h4_path = Path("data/processed/XAUUSD_H4_clean.csv")
    if not h4_path.exists():
        pytest.skip("H4 clean dataset not found")

    h4_df = pd.read_csv(h4_path)
    engine = HTFDirectionalBiasEngine(h4_df)

    # Pick a timestamp well into the dataset where D1 and H4 have breaks
    t = pd.Timestamp("2024-06-01 12:00:00+00:00")
    bias_res = engine.evaluate_bias(t)

    # Create synthetic candidates at this timestamp
    long_cand = SMCSetupCandidate(
        direction=SMCDirection.BULLISH,
        sweep_index=5,
        sweep_time=t - pd.Timedelta(hours=2),
        choch_index=8,
        choch_time=t - pd.Timedelta(hours=1),
        order_block_origin_index=6,
        order_block_created_index=8,
        order_block_created_time=t - pd.Timedelta(hours=1),
        signal_index=10,
        signal_time=t - pd.Timedelta(minutes=15),
        entry_reference_price=2300.0,
        stop_loss_reference=2290.0,
        take_profit_reference=2320.0,
        target_source="fixed_rr",
        risk_distance=10.0,
        reward_risk_ratio=2.0,
        next_bar_open=2300.0,
        next_bar_time=t,
    )
    short_cand = SMCSetupCandidate(
        direction=SMCDirection.BEARISH,
        sweep_index=5,
        sweep_time=t - pd.Timedelta(hours=2),
        choch_index=8,
        choch_time=t - pd.Timedelta(hours=1),
        order_block_origin_index=6,
        order_block_created_index=8,
        order_block_created_time=t - pd.Timedelta(hours=1),
        signal_index=11,
        signal_time=t - pd.Timedelta(minutes=15),
        entry_reference_price=2300.0,
        stop_loss_reference=2310.0,
        take_profit_reference=2280.0,
        target_source="fixed_rr",
        risk_distance=10.0,
        reward_risk_ratio=2.0,
        next_bar_open=2300.0,
        next_bar_time=t,
    )

    accepted, funnel, audit_rows = engine.filter_candidates([long_cand, short_cand], lower_timeframe="M15")

    assert funnel["input_candidates"] == 2
    assert len(audit_rows) == 2

    if bias_res.is_aligned and bias_res.bias == SMCDirection.BULLISH:
        assert long_cand in accepted
        assert short_cand not in accepted
        assert audit_rows[1]["rejection_reason"] == "candidate_direction_mismatch"
    elif bias_res.is_aligned and bias_res.bias == SMCDirection.BEARISH:
        assert short_cand in accepted
        assert long_cand not in accepted
        assert audit_rows[0]["rejection_reason"] == "candidate_direction_mismatch"
    else:
        assert len(accepted) == 0
