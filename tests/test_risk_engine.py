"""Unit tests for the GoldFlow Risk Engine and Trade Management."""
from __future__ import annotations

import pandas as pd
import pytest

from src.risk.engine import (
    DailyDrawdownTracker,
    REJECTED_DAILY_DRAWDOWN_LIMIT,
    REJECTED_MAX_CONCURRENCY,
    REJECTED_SPREAD_TOO_HIGH,
    RiskConfig,
    RiskEngine,
)
from src.risk.trade_management import (
    adjust_candidate_with_atr,
    check_breakeven_trigger,
    compute_atr,
)
from src.smc.models import SMCDirection
from src.strategy.smc_setups import SMCSetupCandidate


def test_risk_engine_concurrency_rejection():
    """When active positions reach max_concurrency, further entries must be rejected."""
    engine = RiskEngine(RiskConfig(max_concurrency=1))
    t = pd.Timestamp("2026-06-16 10:00:00", tz="UTC")

    approved, lots, reason = engine.validate_candidate_entry(
        entry_time=t,
        entry_price=2300.0,
        stop_loss=2295.0,
        spread_usd=0.20,
        active_positions_count=1,
        current_equity=10_000.0,
    )
    assert not approved
    assert reason == REJECTED_MAX_CONCURRENCY


def test_risk_engine_spread_threshold_rejection():
    """Spreads exceeding max_spread_dollars ($0.35) must be rejected."""
    engine = RiskEngine(RiskConfig(max_spread_dollars=0.35))
    t = pd.Timestamp("2026-06-16 10:00:00", tz="UTC")

    approved, lots, reason = engine.validate_candidate_entry(
        entry_time=t,
        entry_price=2300.0,
        stop_loss=2295.0,
        spread_usd=0.45,  # Exceeds $0.35 limit
        active_positions_count=0,
        current_equity=10_000.0,
    )
    assert not approved
    assert reason == REJECTED_SPREAD_TOO_HIGH


def test_daily_drawdown_circuit_breaker_and_utc_reset():
    """Losing 2% ($200 on $10k) trips breaker; resets on next UTC calendar day."""
    engine = RiskEngine(RiskConfig(account_equity=10_000.0, max_daily_drawdown_pct=0.02))
    t_day1_morning = pd.Timestamp("2026-06-16 09:00:00", tz="UTC")
    t_day1_noon = pd.Timestamp("2026-06-16 12:00:00", tz="UTC")
    t_day2_morning = pd.Timestamp("2026-06-17 08:00:00", tz="UTC")

    # Initial state: clear
    assert not engine.tracker.is_circuit_breaker_active(t_day1_morning, 10_000.0)

    # First trade loss: -$100 (1.0% loss) -> breaker still False
    engine.tracker.on_trade_closed(t_day1_morning, net_pnl=-100.0, new_equity=9900.0)
    assert not engine.tracker.is_circuit_breaker_active(t_day1_morning, 9900.0)

    # Second trade loss: -$120 (total loss -$220 > $200) -> breaker TRIPS
    engine.tracker.on_trade_closed(t_day1_noon, net_pnl=-120.0, new_equity=9780.0)
    assert engine.tracker.is_circuit_breaker_active(t_day1_noon, 9780.0)

    # Further trade entry on day 1 is blocked
    approved, lots, reason = engine.validate_candidate_entry(
        entry_time=t_day1_noon + pd.Timedelta(minutes=30),
        entry_price=2300.0,
        stop_loss=2295.0,
        spread_usd=0.20,
        active_positions_count=0,
        current_equity=9780.0,
    )
    assert not approved
    assert reason == REJECTED_DAILY_DRAWDOWN_LIMIT

    # On Day 2 (00:00 UTC rollover), circuit breaker resets automatically
    assert not engine.tracker.is_circuit_breaker_active(t_day2_morning, 9780.0)
    approved_day2, lots_day2, reason_day2 = engine.validate_candidate_entry(
        entry_time=t_day2_morning,
        entry_price=2300.0,
        stop_loss=2295.0,
        spread_usd=0.20,
        active_positions_count=0,
        current_equity=9780.0,
    )
    assert approved_day2
    assert reason_day2 is None


def test_atr_stop_loss_expansion():
    """When structural stop is narrower than 1.5 * ATR, expand stop to 1.5 * ATR."""
    t = pd.Timestamp("2026-06-16 10:00:00", tz="UTC")
    cand = SMCSetupCandidate(
        direction=SMCDirection.BULLISH,
        sweep_index=5,
        sweep_time=t - pd.Timedelta(hours=1),
        choch_index=8,
        choch_time=t - pd.Timedelta(minutes=30),
        order_block_origin_index=6,
        order_block_created_index=8,
        order_block_created_time=t - pd.Timedelta(minutes=30),
        signal_index=10,
        signal_time=t - pd.Timedelta(minutes=15),
        entry_reference_price=2300.0,
        stop_loss_reference=2298.0,  # $2.00 structural distance
        take_profit_reference=2304.0, # 2.0 R = $4.00
        target_source="fixed_rr",
        risk_distance=2.0,
        reward_risk_ratio=2.0,
        next_bar_open=2300.0,
        next_bar_time=t,
    )
    # ATR is $3.00 -> 1.5 * ATR = $4.50 min stop distance
    current_atr = 3.0
    adjusted = adjust_candidate_with_atr(cand, current_atr, min_atr_multiple=1.5, fixed_rr=2.0)

    assert adjusted.risk_distance == 4.50
    assert adjusted.stop_loss_reference == 2300.0 - 4.50  # 2295.50
    assert adjusted.take_profit_reference == 2300.0 + 2.0 * 4.50  # 2309.00
    assert adjusted.target_source == "atr_expanded_fixed_rr"


def test_breakeven_trigger():
    """Moving stop loss to breakeven + buffer when 1.5R favorable excursion is reached."""
    position = {
        "side": "LONG",
        "entry_price": 2300.0,
        "stop_loss": 2295.0,  # $5.00 distance -> 1.5R target = 2300 + 7.50 = 2307.50
    }
    # Price reached 2306.00 (< 2307.50) -> trigger should not fire
    fired, new_sl = check_breakeven_trigger(position, current_high=2306.0, current_low=2298.0, be_r_trigger=1.5)
    assert not fired
    assert new_sl == 2295.0

    # Price reached 2308.00 (>= 2307.50) -> trigger fires, moves SL to entry + 0.05
    fired, new_sl = check_breakeven_trigger(position, current_high=2308.0, current_low=2298.0, be_r_trigger=1.5, be_buffer_usd=0.05)
    assert fired
    assert new_sl == 2300.05

