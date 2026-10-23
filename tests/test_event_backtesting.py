from __future__ import annotations

import pandas as pd
import pytest

from src.backtesting.engine import BacktestConfig, run_event_backtest


def bars(rows, spread=20):
    return pd.DataFrame(
        [
            {
                "time": pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(minutes=5 * i),
                "open": r[0], "high": r[1], "low": r[2], "close": r[3], "spread": spread,
            }
            for i, r in enumerate(rows)
        ]
    )


def candidate(signal_index=0, direction="BULLISH", stop=99.0, target=102.0, setup_id="T1"):
    return {
        "setup_id": setup_id,
        "signal_index": signal_index,
        "signal_time": pd.Timestamp("2026-01-01T00:00:00Z") + pd.Timedelta(minutes=5 * signal_index),
        "direction": direction,
        "stop_loss_reference": stop,
        "take_profit_reference": target,
        "target_source": "fixed_rr_fallback",
    }


def test_entry_is_next_bar_open_with_spread_slippage_and_size():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 101.0, 99.5, 100.5),
        (100.5, 102.2, 100.2, 102),
    ])
    result = run_event_backtest(frame, [candidate()], BacktestConfig(initial_capital=10_000), timeframe="M5")
    trade = next(t for t in result.trades if t["status"] == "CLOSED")
    assert trade["entry_index"] == 1
    assert trade["entry_price"] == pytest.approx(100.25)  # ask + slippage
    assert trade["entry_spread_usd"] == pytest.approx(0.20)
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert trade["lots"] == pytest.approx(0.76)
    assert trade["net_pnl"] > 0
    # R-multiple must use the actual stop-risk after lot-step rounding, not the
    # pre-rounding budget (which can be slightly larger).
    assert trade["R_multiple"] == pytest.approx(
        trade["net_pnl"] / trade["estimated_stop_risk_cash"]
    )
    assert trade["estimated_stop_risk_cash"] <= trade["risk_budget_cash"]


def test_same_bar_stop_target_collision_is_conservatively_stop_first():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 102.0, 98.0, 100),
    ])
    result = run_event_backtest(frame, [candidate(target=101.0)], BacktestConfig())
    trade = next(t for t in result.trades if t["status"] == "CLOSED")
    assert trade["exit_reason"] == "STOP_FIRST_COLLISION"
    assert trade["exit_price"] == pytest.approx(98.95)
    assert trade["net_pnl"] < 0


def test_short_stop_trigger_uses_ask_quote_and_adverse_slippage():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 100.6, 99.0, 100),
        (100.5, 101.9, 100.0, 101),
    ], spread=20)
    result = run_event_backtest(frame, [candidate(direction="BEARISH", stop=102, target=98)], BacktestConfig())
    trade = next(t for t in result.trades if t["status"] == "CLOSED")
    assert trade["exit_reason"] == "STOP_LOSS"
    assert trade["exit_price"] == pytest.approx(102.05)
    assert trade["net_pnl"] < 0


def test_candidate_without_next_bar_is_logged_as_skipped():
    frame = bars([(100, 100.5, 99.5, 100)])
    result = run_event_backtest(frame, [candidate(signal_index=0)], BacktestConfig())
    assert len(result.trades) == 1
    assert result.trades[0]["status"] == "SKIPPED"
    assert result.trades[0]["skip_reason"] == "no_next_bar"


def test_concurrency_cap_rejects_second_same_open_candidate():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
    ])
    result = run_event_backtest(
        frame,
        [candidate(setup_id="A", stop=95, target=110), candidate(setup_id="B", direction="BEARISH", stop=105, target=90)],
        BacktestConfig(max_concurrent_positions=1),
    )
    statuses = {t["setup_id"]: t["status"] for t in result.trades}
    reasons = {t["setup_id"]: t.get("skip_reason") for t in result.trades}
    assert statuses["A"] == "CLOSED"  # end-of-data close
    assert statuses["B"] == "SKIPPED"
    assert reasons["B"] == "max_concurrent_positions"
    assert result.metrics["max_open_positions_observed"] <= 1


def test_cost_adjusted_invalid_trade_is_rejected():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
    ])
    # Long target is below the executable ask-plus-slippage entry.
    result = run_event_backtest(frame, [candidate(stop=99, target=100.1)], BacktestConfig())
    assert result.trades[0]["status"] == "SKIPPED"
    assert result.trades[0]["skip_reason"] == "invalid_stop_or_target_after_fill_costs"


def test_pretriggered_short_stop_at_ask_open_is_rejected():
    frame = bars([
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 99.5, 100.0),
    ], spread=20)
    # ask_open = 100.20, so this short's stop at 100.10 is already triggered
    # at the entry quote and must be rejected, not recorded as a STOP_GAP.
    result = run_event_backtest(
        frame,
        [candidate(direction="BEARISH", stop=100.10, target=95.0, setup_id="SHORT_PRETRIGGERED")],
        BacktestConfig(point_size=0.01, slippage_per_side_usd=0.05),
    )
    trade = result.trades[0]
    assert trade["setup_id"] == "SHORT_PRETRIGGERED"
    assert trade["status"] == "SKIPPED"
    assert trade["skip_reason"] == "invalid_stop_or_target_after_fill_costs"


def test_pretriggered_long_stop_at_bid_open_is_rejected():
    frame = bars([
        (100.0, 100.5, 99.5, 100.0),
        (100.0, 100.5, 99.5, 100.0),
    ], spread=20)
    # bid_open = 100.00, so a long's stop at 100.10 is already breached.
    result = run_event_backtest(
        frame,
        [candidate(direction="BULLISH", stop=100.10, target=105.0, setup_id="LONG_PRETRIGGERED")],
        BacktestConfig(point_size=0.01, slippage_per_side_usd=0.05),
    )
    trade = result.trades[0]
    assert trade["setup_id"] == "LONG_PRETRIGGERED"
    assert trade["status"] == "SKIPPED"
    assert trade["skip_reason"] == "invalid_stop_or_target_after_fill_costs"


def test_round_turn_commission_is_deducted_from_net_pnl():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 101.0, 99.5, 100.5),
        (100.5, 102.2, 100.2, 102),
    ])
    base = run_event_backtest(frame, [candidate()], BacktestConfig())
    charged = run_event_backtest(frame, [candidate()], BacktestConfig(commission_per_lot_per_side=3.0))
    base_trade = next(t for t in base.trades if t["status"] == "CLOSED")
    fee_trade = next(t for t in charged.trades if t["status"] == "CLOSED")
    assert fee_trade["commission"] == pytest.approx(2 * 3 * fee_trade["lots"])
    assert fee_trade["net_pnl"] == pytest.approx(fee_trade["gross_pnl"] - fee_trade["commission"])
    assert fee_trade["lots"] <= base_trade["lots"]  # commission is included in risk sizing


def test_non_chronological_or_invalid_ohlc_is_rejected():
    frame = bars([(100, 100.5, 99.5, 100), (100, 101, 99, 100)])
    frame.loc[1, "time"] = frame.loc[0, "time"]
    with pytest.raises(ValueError, match="unique and chronological"):
        run_event_backtest(frame, [], BacktestConfig())
    frame = bars([(100, 100.5, 99.5, 100), (100, 99, 101, 100)])
    with pytest.raises(ValueError, match="invalid OHLC"):
        run_event_backtest(frame, [], BacktestConfig())


def test_stop_gap_can_exceed_planned_risk_budget_and_is_counted():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
        (98, 99, 97, 98),  # gaps below long stop at 99
    ])
    result = run_event_backtest(
        frame,
        [candidate(stop=99, target=110)],
        BacktestConfig(initial_capital=10_000, risk_fraction=0.01),
    )
    trade = next(t for t in result.trades if t["status"] == "CLOSED")
    assert trade["exit_reason"] == "STOP_GAP"
    assert trade["risk_budget_breach"] is True
    assert result.metrics["losses_beyond_risk_budget"] == 1


def test_end_of_data_mark_is_separated_from_stop_target_win_rate():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 101, 99.5, 101),
    ])
    result = run_event_backtest(
        frame,
        [candidate(stop=95, target=110)],
        BacktestConfig(initial_capital=10_000),
    )
    trade = next(t for t in result.trades if t["status"] == "CLOSED")
    assert trade["exit_reason"] == "END_OF_DATA"
    assert trade["net_pnl"] > 0
    assert result.metrics["end_of_data_exits"] == 1
    assert result.metrics["rule_exit_trades"] == 0
    assert result.metrics["win_rate_pct"] is None
    assert result.metrics["end_of_data_pnl"] == pytest.approx(trade["net_pnl"])


def test_mark_to_market_drawdown_captures_floating_loss_recovered_before_exit():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 101.0, 99.5, 100.0),
        (100.0, 101.0, 96.0, 96.0),  # floating loss; stop at 95 remains untouched
        (96.0, 110.5, 95.5, 110.0),  # target hit without stop collision
    ])
    result = run_event_backtest(frame, [candidate(stop=95.0, target=110.0)], BacktestConfig())
    trade = next(t for t in result.trades if t["status"] == "CLOSED")
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert result.metrics["net_profit"] > 0
    assert result.metrics["max_realized_drawdown_cash"] == pytest.approx(0.0)
    assert result.metrics["max_drawdown_cash"] > 70.0
    assert len(result.equity_curve) == len(frame)
    assert min(point["equity"] for point in result.equity_curve) < 9_950.0


def test_entry_sizing_does_not_use_exit_pnl_from_later_same_bar():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 101.0, 99.5, 100.5),
        (100, 120.5, 99.5, 120.0),  # first position's target exits during this bar
        (120, 121.0, 119.0, 120.0),
    ])
    first = candidate(signal_index=0, stop=95.0, target=120.0, setup_id="FIRST")
    second = candidate(signal_index=1, stop=99.0, target=130.0, setup_id="SECOND")
    result = run_event_backtest(
        frame, [first, second],
        BacktestConfig(initial_capital=10_000.0, max_concurrent_positions=2),
    )
    closed = {t["setup_id"]: t for t in result.trades if t["status"] == "CLOSED"}
    assert closed["FIRST"]["exit_reason"] == "TAKE_PROFIT"
    # 1% of the balance carried into the bar sizes this entry: $100 / ~$130
    # per-lot stop risk, rounded down to 0.01. A same-bar realized win must not
    # increase the new position's risk budget before the bar's open.
    assert closed["SECOND"]["risk_budget_cash"] == pytest.approx(100.0)
    assert closed["SECOND"]["lots"] == pytest.approx(0.76)


def test_time_stop_closes_at_bar_close_after_limit_and_counts_as_rule_exit():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 101.0, 99.5, 100.5),
        (100.5, 101.0, 99.8, 100.7),
        (100.7, 101.0, 100.0, 100.8),
    ])
    result = run_event_backtest(
        frame,
        [candidate(stop=98.0, target=110.0)],
        BacktestConfig(max_holding_bars=2),
    )
    trade = next(t for t in result.trades if t["status"] == "CLOSED")
    assert trade["exit_reason"] == "TIME_STOP"
    assert trade["exit_index"] == 2
    assert trade["bars_held"] == 2  # entry bar counts as 1
    assert trade["exit_price"] == pytest.approx(100.65)
    assert result.metrics["time_stop_exits"] == 1
    assert result.metrics["rule_exit_trades"] == 1
    assert result.metrics["end_of_data_exits"] == 0
    assert result.metrics["max_holding_bars_configured"] == 2


def test_stop_or_target_takes_precedence_over_time_stop_on_same_bar():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 102.5, 99.5, 101.5),  # target touched on entry bar
    ])
    result = run_event_backtest(
        frame,
        [candidate(stop=98.0, target=102.0)],
        BacktestConfig(max_holding_bars=1),
    )
    trade = next(t for t in result.trades if t["status"] == "CLOSED")
    assert trade["exit_reason"] == "TAKE_PROFIT"
    assert result.metrics["time_stop_exits"] == 0


def test_short_time_stop_exits_at_ask_close_plus_slippage():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
    ], spread=20)
    frame.loc[1, "spread"] = 30  # $0.30/oz at point_size=$0.01
    result = run_event_backtest(
        frame,
        [candidate(direction="BEARISH", stop=105.0, target=90.0)],
        BacktestConfig(max_holding_bars=1),
    )
    trade = next(t for t in result.trades if t["status"] == "CLOSED")
    assert trade["exit_reason"] == "TIME_STOP"
    assert trade["exit_price"] == pytest.approx(100.0 + 0.30 + 0.05)
    assert trade["exit_spread_usd"] == pytest.approx(0.30)


@pytest.mark.parametrize("bad_value", [0, -1, 1.5, True, "4"])
def test_invalid_max_holding_bars_is_rejected(bad_value):
    with pytest.raises(ValueError, match="max_holding_bars"):
        BacktestConfig(max_holding_bars=bad_value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("initial_capital", float("nan")),
        ("initial_capital", float("inf")),
        ("contract_size_oz", float("nan")),
        ("point_size", float("inf")),
        ("fallback_spread_usd", float("nan")),
        ("slippage_per_side_usd", float("inf")),
        ("commission_per_lot_per_side", float("nan")),
        ("min_lot", float("inf")),
        ("lot_step", float("nan")),
        ("max_lots", float("inf")),
    ],
)
def test_nonfinite_numeric_config_is_rejected(field, value):
    with pytest.raises(ValueError, match="finite real number"):
        BacktestConfig(**{field: value})


def test_nonfinite_spread_is_rejected_instead_of_silently_using_fallback():
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
    ])
    frame["spread"] = frame["spread"].astype(float)
    frame.loc[1, "spread"] = float("inf")
    with pytest.raises(ValueError, match="spread values must be finite"):
        run_event_backtest(frame, [candidate()], BacktestConfig())


@pytest.mark.parametrize(
    "bad_candidate",
    [
        candidate(stop=float("nan")),
        candidate(target=float("inf")),
        candidate(stop=-1.0),
    ],
)
def test_nonfinite_or_nonpositive_candidate_levels_are_rejected(bad_candidate):
    frame = bars([
        (100, 100.5, 99.5, 100),
        (100, 100.5, 99.5, 100),
    ])
    with pytest.raises(ValueError, match="finite, positive stop-loss and take-profit"):
        run_event_backtest(frame, [bad_candidate], BacktestConfig())


def test_string_numeric_backtest_config_is_rejected_cleanly():
    with pytest.raises(ValueError, match="finite real number"):
        BacktestConfig(point_size="0.01")


def test_noninteger_concurrency_config_is_rejected():
    with pytest.raises(ValueError, match="integer >= 1"):
        BacktestConfig(max_concurrent_positions=1.5)


def test_tick_value_and_volume_scaling_pnl_accounting():
    """
    Verifies that the backtesting engine's contract-size P&L formula:
    gross_pnl = (exit - entry) * direction_sign * contract_size * lots
    produces exact linear tick scaling for 1.0, 0.5, 0.1, and 0.01 lots.
    """
    from src.backtesting.engine import _finalize_trade
    import pandas as pd

    config = BacktestConfig(
        contract_size_oz=100.0,
        point_size=0.01,
        commission_per_lot_per_side=2.5,
    )
    frame = pd.DataFrame([{
        "time": pd.Timestamp("2026-10-20T12:00:00Z"),
        "open": 2650.00, "high": 2650.10, "low": 2649.90, "close": 2650.00,
    }])

    # 1.0 lot, 1-tick ($0.01) favorable move (2650.00 -> 2650.01)
    pos_1lot = {
        "side": "LONG",
        "entry_index": 0,
        "entry_price": 2650.00,
        "entry_reference_open": 2650.00,
        "entry_spread_usd": 0.0,
        "entry_spread_source": "test",
        "stop_loss": 2640.00,
        "take_profit": 2660.00,
        "lots": 1.0,
        "risk_budget_cash": 100.0,
        "estimated_stop_risk_cash": 1000.0,
        "signal_index": 0,
        "signal_time": "2026-10-20T11:45:00Z",
        "audit_fields": {"setup_id": "TEST_001"},
    }
    trade, _ = _finalize_trade(
        pos_1lot,
        {"exit_index": 0, "exit_price": 2650.01, "exit_reason": "TAKE_PROFIT"},
        frame,
        equity=10_000.0,
        config=config,
    )
    assert round(trade["gross_pnl"], 4) == 1.00  # $1.00 USD/tick for 1.0 lot
    assert round(trade["commission"], 4) == 5.00  # 2 * 2.5 * 1.0 lot
    assert round(trade["net_pnl"], 4) == -4.00

    # 0.1 lot, 1-tick move
    pos_01lot = dict(pos_1lot, lots=0.1)
    trade_01, _ = _finalize_trade(
        pos_01lot,
        {"exit_index": 0, "exit_price": 2650.01, "exit_reason": "TAKE_PROFIT"},
        frame,
        equity=10_000.0,
        config=config,
    )
    assert round(trade_01["gross_pnl"], 4) == 0.10  # $0.10 USD/tick for 0.1 lot

    # 0.01 lot, 1-tick move
    pos_001lot = dict(pos_1lot, lots=0.01)
    trade_001, _ = _finalize_trade(
        pos_001lot,
        {"exit_index": 0, "exit_price": 2650.01, "exit_reason": "TAKE_PROFIT"},
        frame,
        equity=10_000.0,
        config=config,
    )
    assert round(trade_001["gross_pnl"], 4) == 0.01  # $0.01 USD/tick for 0.01 lot

    # 1.0 lot, SELL favorable move (2650.00 -> 2649.99)
    pos_sell = dict(pos_1lot, side="SHORT")
    trade_sell, _ = _finalize_trade(
        pos_sell,
        {"exit_index": 0, "exit_price": 2649.99, "exit_reason": "TAKE_PROFIT"},
        frame,
        equity=10_000.0,
        config=config,
    )
    assert round(trade_sell["gross_pnl"], 4) == 1.00  # $1.00 USD/tick favorable for SELL


def test_intrabar_stop_target_collision_conservative_resolution():
    """
    When a bar touches both stop and target, conservative_stop_first=True must
    resolve the collision as a stop-loss, not a take-profit.
    """
    # Bar 0: signal, Bar 1: entry, Bar 2: collision (high touches target, low touches stop)
    frame = bars([
        (100.0, 100.2, 99.8, 100.0),   # bar 0: signal
        (100.0, 100.5, 99.5, 100.0),   # bar 1: entry
        (100.0, 105.0, 95.0, 100.0),   # bar 2: touches target (102) and stop (98)
    ])
    cand = candidate(signal_index=0, direction="BULLISH", stop=98.0, target=102.0)

    # Conservative: stop-first
    res_cons = run_event_backtest(
        frame, [cand],
        BacktestConfig(conservative_stop_first=True, fallback_spread_usd=0.0, slippage_per_side_usd=0.0),
    )
    assert res_cons.trades[0]["exit_reason"] == "STOP_FIRST_COLLISION"
    assert res_cons.trades[0]["exit_price"] == 98.0
    assert res_cons.trades[0]["net_pnl"] < 0

    # Non-conservative: target-first
    res_agg = run_event_backtest(
        frame, [cand],
        BacktestConfig(conservative_stop_first=False, fallback_spread_usd=0.0, slippage_per_side_usd=0.0),
    )
    assert res_agg.trades[0]["exit_reason"] == "TARGET_FIRST_COLLISION"
    assert res_agg.trades[0]["exit_price"] == 102.0
    assert res_agg.trades[0]["net_pnl"] > 0

