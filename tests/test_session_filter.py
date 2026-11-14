"""Unit tests for the Session Liquidity Filter."""
from __future__ import annotations

import pandas as pd
import pytest

from src.smc.models import SMCDirection
from src.strategy.session_filter import SessionFilterConfig, SessionLiquidityFilter
from src.strategy.smc_setups import SMCSetupCandidate


def test_asian_session_rejected():
    """Asian session timestamps (e.g. 03:00 UTC on Tuesday) must be rejected."""
    filter_ = SessionLiquidityFilter()
    t = pd.Timestamp("2026-04-14 03:00:00", tz="UTC")  # Tuesday
    eligible, session, reason = filter_.evaluate_timestamp(t)
    assert not eligible
    assert session is None
    assert reason == "asian_session_excluded"


def test_london_session_accepted():
    """London morning peak (08:30 UTC in winter / 07:30 UTC in summer BST) must be accepted."""
    filter_ = SessionLiquidityFilter()
    # Summer (BST = UTC+1): 08:30 BST is 07:30 UTC
    t_summer = pd.Timestamp("2026-06-16 07:30:00", tz="UTC")  # Tuesday
    eligible, session, reason = filter_.evaluate_timestamp(t_summer)
    assert eligible
    assert "LONDON" in session
    assert reason is None

    # Winter (GMT = UTC): 08:30 GMT is 08:30 UTC
    t_winter = pd.Timestamp("2026-01-13 08:30:00", tz="UTC")  # Tuesday
    eligible, session, reason = filter_.evaluate_timestamp(t_winter)
    assert eligible
    assert "LONDON" in session
    assert reason is None


def test_new_york_session_accepted():
    """New York cash open (09:30 NY time) must be accepted."""
    filter_ = SessionLiquidityFilter()
    # Summer (EDT = UTC-4): 09:30 EDT is 13:30 UTC
    t_summer = pd.Timestamp("2026-06-16 13:30:00", tz="UTC")  # Tuesday
    eligible, session, reason = filter_.evaluate_timestamp(t_summer)
    assert eligible
    assert "NEW_YORK" in session
    assert reason is None

    # Winter (EST = UTC-5): 09:30 EST is 14:30 UTC
    t_winter = pd.Timestamp("2026-01-13 14:30:00", tz="UTC")  # Tuesday
    eligible, session, reason = filter_.evaluate_timestamp(t_winter)
    assert eligible
    assert "NEW_YORK" in session
    assert reason is None


def test_post_ny_dead_zone_rejected():
    """Post-NY evening timestamps (e.g. 21:00 UTC) must be rejected."""
    filter_ = SessionLiquidityFilter()
    t = pd.Timestamp("2026-06-16 21:00:00", tz="UTC")
    eligible, session, reason = filter_.evaluate_timestamp(t)
    assert not eligible
    assert reason == "post_ny_dead_zone"


def test_weekend_market_closed():
    """Saturday and Sunday timestamps must be rejected."""
    filter_ = SessionLiquidityFilter()
    t_sat = pd.Timestamp("2026-06-20 08:30:00", tz="UTC")  # Saturday
    eligible, session, reason = filter_.evaluate_timestamp(t_sat)
    assert not eligible
    assert reason == "weekend_market_closed"


def test_session_filter_candidates():
    """Candidate filtering must accept valid session entries and log rejected ones."""
    filter_ = SessionLiquidityFilter()
    t_good = pd.Timestamp("2026-06-16 08:30:00", tz="UTC")  # London session
    t_bad = pd.Timestamp("2026-06-16 03:00:00", tz="UTC")   # Asian session

    c1 = SMCSetupCandidate(
        direction=SMCDirection.BULLISH,
        sweep_index=5,
        sweep_time=t_good - pd.Timedelta(hours=1),
        choch_index=8,
        choch_time=t_good - pd.Timedelta(minutes=30),
        order_block_origin_index=6,
        order_block_created_index=8,
        order_block_created_time=t_good - pd.Timedelta(minutes=30),
        signal_index=10,
        signal_time=t_good - pd.Timedelta(minutes=15),
        entry_reference_price=2300.0,
        stop_loss_reference=2290.0,
        take_profit_reference=2320.0,
        target_source="fixed_rr",
        risk_distance=10.0,
        reward_risk_ratio=2.0,
        next_bar_open=2300.0,
        next_bar_time=t_good,
    )
    c2 = SMCSetupCandidate(
        direction=SMCDirection.BEARISH,
        sweep_index=25,
        sweep_time=t_bad - pd.Timedelta(hours=1),
        choch_index=28,
        choch_time=t_bad - pd.Timedelta(minutes=30),
        order_block_origin_index=26,
        order_block_created_index=28,
        order_block_created_time=t_bad - pd.Timedelta(minutes=30),
        signal_index=30,
        signal_time=t_bad - pd.Timedelta(minutes=15),
        entry_reference_price=2300.0,
        stop_loss_reference=2310.0,
        take_profit_reference=2280.0,
        target_source="fixed_rr",
        risk_distance=10.0,
        reward_risk_ratio=2.0,
        next_bar_open=2300.0,
        next_bar_time=t_bad,
    )

    accepted, funnel, audit_rows = filter_.filter_candidates([c1, c2], lower_timeframe="M15")
    assert len(accepted) == 1
    assert accepted[0] == c1
    assert funnel["accepted_candidates"] == 1
    assert funnel["rejected_candidates"] == 1
    assert funnel["rejection_reasons"]["asian_session_excluded"] == 1
    assert audit_rows[0]["accepted"] is True
    assert audit_rows[1]["accepted"] is False

