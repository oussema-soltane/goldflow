"""Unit tests for the High-Impact Economic News Filter."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from src.smc.models import SMCDirection
from src.strategy.news_filter import HighImpactNewsFilter, NewsFilterConfig
from src.strategy.smc_setups import SMCSetupCandidate


@pytest.fixture
def sample_news_df():
    events = [
        {
            "timestamp_utc": "2026-06-05 12:30:00+00:00",
            "event_name": "Non-Farm Payrolls (NFP)",
            "currency": "USD",
            "impact_level": "HIGH",
        },
        {
            "timestamp_utc": "2026-06-10 12:30:00+00:00",
            "event_name": "Consumer Price Index (CPI)",
            "currency": "USD",
            "impact_level": "HIGH",
        },
    ]
    return pd.DataFrame(events)


def test_news_blackout_pre_event(sample_news_df):
    """Entry 10 minutes before NFP must be blocked."""
    filter_ = HighImpactNewsFilter(calendar_source=sample_news_df)
    t = pd.Timestamp("2026-06-05 12:20:00+00:00")
    blocked, event_name, reason, rel_mins = filter_.evaluate_timestamp(t)
    assert blocked
    assert event_name == "Non-Farm Payrolls (NFP)"
    assert "news_blackout:Non-Farm Payrolls (NFP)" in reason
    assert rel_mins == -10.0


def test_news_blackout_post_event(sample_news_df):
    """Entry 20 minutes after CPI must be blocked (post-news buffer is 30m)."""
    filter_ = HighImpactNewsFilter(calendar_source=sample_news_df)
    t = pd.Timestamp("2026-06-10 12:50:00+00:00")
    blocked, event_name, reason, rel_mins = filter_.evaluate_timestamp(t)
    assert blocked
    assert event_name == "Consumer Price Index (CPI)"
    assert "news_blackout:Consumer Price Index (CPI)" in reason
    assert rel_mins == 20.0


def test_news_clear_window(sample_news_df):
    """Entry 2 hours before or after an event must not be blocked."""
    filter_ = HighImpactNewsFilter(calendar_source=sample_news_df)
    t = pd.Timestamp("2026-06-05 15:00:00+00:00")
    blocked, event_name, reason, rel_mins = filter_.evaluate_timestamp(t)
    assert not blocked
    assert reason is None
    assert rel_mins == 150.0  # 2.5 hours after event


def test_news_fail_closed_missing_calendar(tmp_path):
    """Missing or empty calendar must fail closed."""
    non_existent = tmp_path / "does_not_exist.csv"
    filter_ = HighImpactNewsFilter(calendar_source=non_existent)
    t = pd.Timestamp("2026-06-05 15:00:00+00:00")
    blocked, event_name, reason, rel_mins = filter_.evaluate_timestamp(t)
    assert blocked
    assert reason == "news_calendar_unloaded_fail_closed"


def test_news_filter_candidates(sample_news_df):
    """Candidate filtering correctly drops news-blackout setups."""
    filter_ = HighImpactNewsFilter(calendar_source=sample_news_df)
    t_clear = pd.Timestamp("2026-06-05 10:00:00+00:00")
    t_news = pd.Timestamp("2026-06-05 12:25:00+00:00")  # 5 mins before NFP

    c1 = SMCSetupCandidate(
        direction=SMCDirection.BULLISH,
        sweep_index=5,
        sweep_time=t_clear - pd.Timedelta(hours=1),
        choch_index=8,
        choch_time=t_clear - pd.Timedelta(minutes=30),
        order_block_origin_index=6,
        order_block_created_index=8,
        order_block_created_time=t_clear - pd.Timedelta(minutes=30),
        signal_index=10,
        signal_time=t_clear - pd.Timedelta(minutes=15),
        entry_reference_price=2300.0,
        stop_loss_reference=2290.0,
        take_profit_reference=2320.0,
        target_source="fixed_rr",
        risk_distance=10.0,
        reward_risk_ratio=2.0,
        next_bar_open=2300.0,
        next_bar_time=t_clear,
    )
    c2 = SMCSetupCandidate(
        direction=SMCDirection.BEARISH,
        sweep_index=25,
        sweep_time=t_news - pd.Timedelta(hours=1),
        choch_index=28,
        choch_time=t_news - pd.Timedelta(minutes=30),
        order_block_origin_index=26,
        order_block_created_index=28,
        order_block_created_time=t_news - pd.Timedelta(minutes=30),
        signal_index=30,
        signal_time=t_news - pd.Timedelta(minutes=15),
        entry_reference_price=2300.0,
        stop_loss_reference=2310.0,
        take_profit_reference=2280.0,
        target_source="fixed_rr",
        risk_distance=10.0,
        reward_risk_ratio=2.0,
        next_bar_open=2300.0,
        next_bar_time=t_news,
    )

    accepted, funnel, audit_rows = filter_.filter_candidates([c1, c2], lower_timeframe="M15")
    assert len(accepted) == 1
    assert accepted[0] == c1
    assert funnel["accepted_candidates"] == 1
    assert funnel["rejected_candidates"] == 1
    assert audit_rows[0]["accepted"] is True
    assert audit_rows[1]["accepted"] is False
    assert "news_blackout" in audit_rows[1]["rejection_reason"]

