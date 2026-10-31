"""Causal-time tests for the experimental H4/H1 SMC context filter."""
from __future__ import annotations

import pandas as pd
import pytest

from src.smc.models import (
    SMCDirection,
    SMCAnalysisResult,
    SMCStructureBreak,
    SMCStructureType,
    SMCSwingPoint,
    SMCSwingType,
)
from src.strategy.smc_mtf import StructureTrendTimeline, filter_candidates_by_mtf
from src.strategy.smc_setups import SMCSetupCandidate


def _event(time: str, direction: SMCDirection, index: int = 0) -> SMCStructureBreak:
    timestamp = pd.Timestamp(time)
    swing = SMCSwingPoint(
        index=index,
        time=timestamp,
        price=2500.0,
        swing_type=SMCSwingType.SWING_HIGH,
        classification="INIT",
        confirmed_index=index,
        confirmed_time=timestamp,
    )
    prior = SMCDirection.BEARISH if direction == SMCDirection.BULLISH else SMCDirection.BULLISH
    return SMCStructureBreak(
        break_type=SMCStructureType.BOS,
        direction=direction,
        broken_swing=swing,
        break_index=index,
        break_time=timestamp,
        break_price=2501.0,
        prior_trend=prior,
        resulting_trend=direction,
    )


def _analysis(timeframe: str, events: list[SMCStructureBreak]) -> SMCAnalysisResult:
    return SMCAnalysisResult(
        symbol="XAUUSD",
        timeframe=timeframe,
        total_bars=max((e.break_index for e in events), default=-1) + 1,
        structure_breaks=events,
    )


def _candidate(direction: SMCDirection, entry_time: str, signal_time: str = "2026-01-05T11:00:00Z") -> SMCSetupCandidate:
    signal_ts = pd.Timestamp(signal_time)
    entry_ts = pd.Timestamp(entry_time)
    return SMCSetupCandidate(
        direction=direction,
        sweep_index=0,
        sweep_time=signal_ts - pd.Timedelta(minutes=30),
        choch_index=1,
        choch_time=signal_ts - pd.Timedelta(minutes=15),
        order_block_origin_index=0,
        order_block_created_index=1,
        order_block_created_time=signal_ts - pd.Timedelta(minutes=15),
        signal_index=2,
        signal_time=signal_ts,
        entry_reference_price=2500.0,
        stop_loss_reference=2498.0,
        take_profit_reference=2504.0,
        target_source="fixed_rr_fallback",
        risk_distance=2.0,
        reward_risk_ratio=2.0,
        next_bar_open=2500.0,
        next_bar_time=entry_ts,
    )


def test_higher_timeframe_event_is_invisible_before_candle_close_and_visible_at_close():
    h1_event = _event("2026-01-05T10:00:00Z", SMCDirection.BULLISH)
    timeline = StructureTrendTimeline.from_analysis(_analysis("H1", [h1_event]), "H1")

    assert timeline.at("2026-01-05T10:59:59Z") is None
    snapshot = timeline.at("2026-01-05T11:00:00Z")
    assert snapshot is not None
    assert snapshot.direction == SMCDirection.BULLISH
    assert snapshot.available_at == pd.Timestamp("2026-01-05T11:00:00Z")


def test_mtf_filter_rejects_context_not_yet_completed_at_entry():
    h4 = _analysis("H4", [_event("2026-01-05T08:00:00Z", SMCDirection.BULLISH)])
    h1 = _analysis("H1", [_event("2026-01-05T10:00:00Z", SMCDirection.BULLISH)])
    candidate = _candidate(SMCDirection.BULLISH, "2026-01-05T11:15:00Z")

    accepted, funnel, audit = filter_candidates_by_mtf(
        [candidate], lower_timeframe="M15", h4_analysis=h4, h1_analysis=h1
    )

    assert accepted == []
    assert funnel["rejection_reasons"] == {"missing_h4_context": 1}
    assert audit[0]["h4_context_available_at"] is None
    assert audit[0]["h1_context_available_at"] == "2026-01-05T11:00:00+00:00"


def test_mtf_filter_accepts_candidate_only_after_both_higher_timeframes_close():
    h4 = _analysis("H4", [_event("2026-01-05T08:00:00Z", SMCDirection.BULLISH)])
    h1 = _analysis("H1", [_event("2026-01-05T11:00:00Z", SMCDirection.BULLISH)])
    candidate = _candidate(SMCDirection.BULLISH, "2026-01-05T12:15:00Z")

    accepted, funnel, audit = filter_candidates_by_mtf(
        [candidate], lower_timeframe="M15", h4_analysis=h4, h1_analysis=h1
    )

    assert accepted == [candidate]
    assert funnel["accepted_candidates"] == 1
    assert audit[0]["accepted"] is True
    assert audit[0]["h4_context_available_at"] == "2026-01-05T12:00:00+00:00"


def test_mtf_filter_rejects_conflicting_h4_h1_context_and_wrong_candidate_direction():
    h4 = _analysis("H4", [_event("2026-01-05T08:00:00Z", SMCDirection.BULLISH)])
    h1_conflict = _analysis("H1", [_event("2026-01-05T11:00:00Z", SMCDirection.BEARISH)])
    bullish = _candidate(SMCDirection.BULLISH, "2026-01-05T12:15:00Z")
    accepted, funnel, _ = filter_candidates_by_mtf(
        [bullish], lower_timeframe="M15", h4_analysis=h4, h1_analysis=h1_conflict
    )
    assert accepted == []
    assert funnel["rejection_reasons"] == {"higher_timeframe_conflict": 1}

    h1_aligned = _analysis("H1", [_event("2026-01-05T11:00:00Z", SMCDirection.BULLISH)])
    bearish = _candidate(SMCDirection.BEARISH, "2026-01-05T12:15:00Z")
    accepted, funnel, _ = filter_candidates_by_mtf(
        [bearish], lower_timeframe="M15", h4_analysis=h4, h1_analysis=h1_aligned
    )
    assert accepted == []
    assert funnel["rejection_reasons"] == {"candidate_direction_mismatch": 1}


def test_execution_audit_paths_are_project_relative_when_possible():
    from scripts.run_smc_mtf_backtest import ROOT, _portable_execution_audit_paths

    audit = {
        "data_dir": str(ROOT / "data" / "processed"),
        "datasets": [
            {"sidecar_path": str(ROOT / "data" / "processed" / "XAUUSD_M5_clean.meta.json")},
            {"symbol": "XAUUSD"},
        ],
    }

    portable = _portable_execution_audit_paths(audit)

    assert portable["data_dir"] == "data/processed"
    assert portable["datasets"][0]["sidecar_path"] == "data/processed/XAUUSD_M5_clean.meta.json"
    assert portable["datasets"][1] == {"symbol": "XAUUSD"}
    # The helper returns a cleaned copy without mutating the audited source object.
    assert audit["data_dir"] == str(ROOT / "data" / "processed")


# ---------------------------------------------------------------------------
# Phase 5.1 regression: data_end_time boundary enforcement (H4/H1 stale context)
# ---------------------------------------------------------------------------

def test_timeline_at_returns_none_beyond_data_end_time():
    """StructureTrendTimeline.at() must return None when decision_time > data_end_time.

    This is the core regression guard for the SMC_M15_0053 data-boundary issue:
    H4 data confirmed end = 2026-10-20T13:00Z; trade entered 2026-10-21T22:30Z
    (33.5 hours later).  With boundary enforcement the timeline returns None,
    blocking that entry from the MTF-confirmed variant.
    """
    h4_event = _event("2026-10-19T08:00:00Z", SMCDirection.BULLISH)
    data_end = pd.Timestamp("2026-10-20T13:00:00+00:00")  # last H4 bar confirmed close
    timeline = StructureTrendTimeline.from_analysis(
        _analysis("H4", [h4_event]), "H4", data_end_time=data_end
    )

    # At the boundary exactly: context must still be available.
    at_boundary = timeline.at("2026-10-20T13:00:00Z")
    assert at_boundary is not None, "Context should be available exactly at the data_end_time boundary"

    # One second after: dataset has ended — must return None (hard boundary).
    after_boundary = timeline.at("2026-10-20T13:00:01Z")
    assert after_boundary is None, (
        "Context must not carry forward after data_end_time. "
        "This guards against the SMC_M15_0053-class error."
    )

    # 33.5 hours after H4 data ends (analogous to SMC_M15_0053 entry time).
    smc_0053_analog = timeline.at("2026-10-21T22:30:00Z")
    assert smc_0053_analog is None, (
        "No H4 context should be available 33.5h after the dataset ended. "
        "SMC_M15_0053-equivalent entries must be rejected."
    )


def test_timeline_at_without_data_end_time_carries_forward_stale_context():
    """Without data_end_time, at() carries forward the last snapshot (documented behavior).

    This test documents the *pre-fix* behavior: when no boundary is set the
    timeline silently returns stale context.  It exists to confirm backward
    compatibility of the API default and to document the risk explicitly.
    """
    h4_event = _event("2026-10-19T08:00:00Z", SMCDirection.BULLISH)
    timeline = StructureTrendTimeline.from_analysis(
        _analysis("H4", [h4_event]), "H4", data_end_time=None
    )
    # Stale carry-forward: returns the last snapshot even far beyond the data end.
    result = timeline.at("2026-10-21T22:30:00Z")
    assert result is not None, (
        "Without data_end_time, stale context carry-forward is expected (documented behavior). "
        "Production pipelines MUST always pass data_end_time to prevent this."
    )


def test_filter_rejects_candidates_beyond_h4_data_boundary():
    """filter_candidates_by_mtf must reject entries beyond the H4 confirmed data end.

    This is the integration-level guard: SMC_M15_0053 entered at 2026-10-21T22:30Z,
    which is 33.5 hours after the H4 dataset's last confirmed candle close
    (2026-10-20T13:00Z). With h4_data_end_time set, the filter must reject it.
    """
    h4_end = pd.Timestamp("2026-10-20T13:00:00+00:00")
    h1_end = pd.Timestamp("2026-10-20T15:00:00+00:00")

    h4 = _analysis("H4", [_event("2026-10-19T08:00:00Z", SMCDirection.BULLISH)])
    h1 = _analysis("H1", [_event("2026-10-20T11:00:00Z", SMCDirection.BULLISH)])

    # Candidate WITHIN boundary: entry at 2026-10-20T12:15Z (before both H4 and H1 ends).
    valid_candidate = _candidate(SMCDirection.BULLISH, "2026-10-20T12:15:00Z",
                                 signal_time="2026-10-20T12:00:00Z")
    # Candidate BEYOND H4 boundary: entry at 2026-10-21T22:30Z (analogous to SMC_M15_0053).
    stale_candidate = _candidate(SMCDirection.BULLISH, "2026-10-21T22:30:00Z",
                                 signal_time="2026-10-21T22:15:00Z")

    accepted, funnel, audit = filter_candidates_by_mtf(
        [valid_candidate, stale_candidate],
        lower_timeframe="M15",
        h4_analysis=h4,
        h1_analysis=h1,
        h4_data_end_time=h4_end,
        h1_data_end_time=h1_end,
    )

    assert len(accepted) == 1, (
        f"Only the in-boundary candidate should be accepted; got {len(accepted)}"
    )
    assert accepted[0] is valid_candidate
    assert "missing_h4_context" in funnel["rejection_reasons"], (
        "The stale candidate must be rejected with missing_h4_context"
    )
    # Verify the audit row for the stale candidate.
    stale_audit = audit[1]
    assert stale_audit["accepted"] is False
    assert stale_audit["rejection_reason"] == "missing_h4_context"
    assert stale_audit["h4_direction"] is None, (
        "h4_direction must be None when entry is beyond the data boundary"
    )
    # Also verify funnel boundary fields.
    assert funnel["data_boundary_h4"] == h4_end.isoformat()
    assert funnel["data_boundary_h1"] == h1_end.isoformat()


def test_filter_boundary_matches_expected_h4_h1_confirmed_ends():
    """Verify actual dataset boundaries: H4 ends 2026-10-20T13:00Z, H1 ends 2026-10-20T15:00Z."""
    from pathlib import Path
    from src.strategy.smc_mtf import TIMEFRAME_DURATIONS

    data_dir = Path(__file__).resolve().parent.parent / "data" / "processed"
    h4_csv = data_dir / "XAUUSD_H4_clean.csv"
    h1_csv = data_dir / "XAUUSD_H1_clean.csv"
    if not h4_csv.exists() or not h1_csv.exists():
        pytest.skip("Processed datasets not found; skipping integration boundary test")

    import pandas as pd
    h4_df = pd.read_csv(h4_csv)
    h1_df = pd.read_csv(h1_csv)
    h4_df["time"] = pd.to_datetime(h4_df["time"], utc=True)
    h1_df["time"] = pd.to_datetime(h1_df["time"], utc=True)

    h4_confirmed_end = h4_df["time"].max() + TIMEFRAME_DURATIONS["H4"]
    h1_confirmed_end = h1_df["time"].max() + TIMEFRAME_DURATIONS["H1"]

    assert h4_confirmed_end == pd.Timestamp("2026-10-20T13:00:00+00:00"), (
        f"Expected H4 confirmed end = 2026-10-20T13:00:00+00:00, got {h4_confirmed_end}"
    )
    assert h1_confirmed_end == pd.Timestamp("2026-10-20T15:00:00+00:00"), (
        f"Expected H1 confirmed end = 2026-10-20T15:00:00+00:00, got {h1_confirmed_end}"
    )


# ---------------------------------------------------------------------------
# Phase 5.1 regression: END_OF_DATA slippage reconciliation
# ---------------------------------------------------------------------------

def test_end_of_data_exit_includes_raw_exit_price_for_reconciliation():
    """END_OF_DATA exit event must include raw_exit_price so that cost-replay matches backtest.

    Before the fix: raw_exit_price was missing from the event dict, causing
    _finalize_trade() to default raw_exit_price = exit_price → exit_slip = 0.0
    (only 1 side of slippage recorded).  The cost-replay applied 2 sides, causing
    a $0.20 systematic discrepancy.  After the fix, both paths agree exactly.
    """
    import pandas as pd
    from src.backtesting.engine import BacktestConfig, run_event_backtest

    # Construct a minimal 5-bar frame so one END_OF_DATA exit occurs.
    bars = [
        {"time": "2026-01-01T10:00:00+00:00", "open": 2500.0, "high": 2520.0, "low": 2490.0, "close": 2510.0},
        {"time": "2026-01-01T10:15:00+00:00", "open": 2510.0, "high": 2530.0, "low": 2508.0, "close": 2518.0},
        {"time": "2026-01-01T10:30:00+00:00", "open": 2518.0, "high": 2540.0, "low": 2510.0, "close": 2525.0},
        {"time": "2026-01-01T10:45:00+00:00", "open": 2525.0, "high": 2545.0, "low": 2515.0, "close": 2535.0},
        {"time": "2026-01-01T11:00:00+00:00", "open": 2535.0, "high": 2550.0, "low": 2525.0, "close": 2540.0},
    ]
    frame = pd.DataFrame(bars)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)

    cfg = BacktestConfig(
        initial_capital=10_000.0,
        contract_size_oz=100.0,
        slippage_per_side_usd=0.05,
        fallback_spread_usd=0.20,
    )

    # Place a LONG candidate that opens at bar 1 and never hits SL/TP → END_OF_DATA exit.
    candidate = {
        "setup_id": "TEST_EOD_LONG",
        "timeframe": "M15",
        "direction": "BULLISH",
        "signal_index": 0,
        "signal_time": "2026-01-01T10:00:00+00:00",
        "stop_loss_reference": 2505.0,   # 5.0 risk distance fits well within risk budget
        "take_profit_reference": 2700.0,  # far away — never hit
        "target_source": "test",
        "entry_reference_price": 2510.0,
        "risk_distance": 5.0,
    }

    result = run_event_backtest(frame, [candidate], cfg, timeframe="M15")
    closed = [t for t in result.trades if t.get("status") == "CLOSED"]
    eod_trades = [t for t in closed if t.get("exit_reason") == "END_OF_DATA"]

    assert len(eod_trades) == 1, f"Expected exactly 1 END_OF_DATA trade, got {len(eod_trades)}"
    eod = eod_trades[0]

    # After the fix, raw_exit_price must be present and differ from exit_price by slippage.
    assert "raw_exit_price" in eod, "END_OF_DATA trade must record raw_exit_price"
    assert abs(eod["raw_exit_price"] - eod["exit_price"]) == pytest.approx(cfg.slippage_per_side_usd, abs=1e-9), (
        f"raw_exit_price - exit_price should equal slippage_per_side_usd ({cfg.slippage_per_side_usd}); "
        f"got raw={eod['raw_exit_price']}, exit={eod['exit_price']}"
    )

    # Cost-replay on the backtest trade must reproduce the exact same net P&L.
    from src.backtesting.engine import replay_trade_ledger_costs
    replay = replay_trade_ledger_costs(
        [eod],
        spread_multiplier=1.0,
        slippage_per_side_usd=cfg.slippage_per_side_usd,
        commission_per_lot_per_side=cfg.commission_per_lot_per_side,
        contract_size_oz=cfg.contract_size_oz,
    )
    # The END_OF_DATA exit has slippage on both sides in replay; backtest must also record both sides.
    backtest_net = float(eod["net_pnl"])
    replay_net = replay["net_profit"]
    assert abs(backtest_net - replay_net) < 0.01, (
        f"Backtest net P&L ({backtest_net:.4f}) must match cost-replay net P&L ({replay_net:.4f}) "
        f"within $0.01. Difference = {abs(backtest_net - replay_net):.4f}. "
        "A non-zero difference indicates raw_exit_price is still missing from the END_OF_DATA event."
    )
