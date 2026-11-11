"""Unit and regression tests for SMC Candidate Fixed R:R with Partial Exits.

Candidate spec: configs/candidate_specs/SMC_CANDIDATE_FIXED_RR_v1.json
Rules:
- Leg A (50% lots): exits at 2R (or partial_exit_at_r)
- Leg B (50% lots): exits at 3R (or remaining_exit_at_r)
- Shared stop loss: invalidation of origin OB
"""

from __future__ import annotations

import math
import pandas as pd
import pytest

from src.backtesting.engine import BacktestConfig, run_event_backtest


def _make_test_bars(n: int = 50, start_price: float = 2000.0) -> pd.DataFrame:
    times = pd.date_range("2026-01-01 00:00:00", periods=n, freq="1h", tz="UTC")
    rows = []
    price = start_price
    for t in times:
        rows.append({
            "time": t,
            "open": price,
            "high": price + 2.0,
            "low": price - 2.0,
            "close": price + 0.5,
            "spread": 0.20,
        })
        price += 0.5
    return pd.DataFrame(rows)


class TestCandidateFixedRRConfig:
    def test_default_config_has_split_disabled(self):
        cfg = BacktestConfig()
        assert cfg.partial_exit_at_r == 0.0
        assert cfg.remaining_exit_at_r == 0.0

    def test_valid_split_config(self):
        cfg = BacktestConfig(partial_exit_at_r=2.0, remaining_exit_at_r=3.0)
        assert cfg.partial_exit_at_r == 2.0
        assert cfg.remaining_exit_at_r == 3.0

    def test_invalid_split_config_rejected(self):
        # remaining <= partial
        with pytest.raises(ValueError, match="partial_exit_at_r must be > 0 and remaining_exit_at_r must be > partial_exit_at_r"):
            BacktestConfig(partial_exit_at_r=3.0, remaining_exit_at_r=2.0)

        with pytest.raises(ValueError, match="partial_exit_at_r must be > 0 and remaining_exit_at_r must be > partial_exit_at_r"):
            BacktestConfig(partial_exit_at_r=2.0, remaining_exit_at_r=2.0)

        with pytest.raises(ValueError, match="partial_exit_at_r must be a finite real number"):
            BacktestConfig(partial_exit_at_r=float("nan"), remaining_exit_at_r=3.0)


class TestCandidateExecutionSplit:
    def test_candidate_trade_splits_into_two_legs(self):
        # Create a synthetic dataset where price rallies from 2000 to 2020
        df = _make_test_bars(30, start_price=2000.0)

        # Bullish candidate at bar 2: stop at 1995 (risk = 5 pts), target = 2025
        candidate = {
            "setup_id": "TEST_001",
            "signal_index": 2,
            "signal_time": str(df["time"].iloc[2]),
            "direction": "BULLISH",
            "stop_loss_reference": 1995.0,
            "take_profit_reference": 2025.0,
            "target_source": "test",
        }

        cfg_baseline = BacktestConfig(initial_capital=10000.0, partial_exit_at_r=0.0, remaining_exit_at_r=0.0)
        res_baseline = run_event_backtest(df, [candidate], cfg_baseline, timeframe="H1")

        cfg_candidate = BacktestConfig(initial_capital=10000.0, partial_exit_at_r=2.0, remaining_exit_at_r=3.0)
        res_candidate = run_event_backtest(df, [candidate], cfg_candidate, timeframe="H1")

        closed_base = [t for t in res_baseline.trades if t.get("status") == "CLOSED"]
        closed_cand = [t for t in res_candidate.trades if t.get("status") == "CLOSED"]

        # Baseline produces 1 trade; Candidate produces 2 legs (_legA and _legB)
        assert len(closed_base) == 1
        assert len(closed_cand) == 2
        setup_ids = [t["setup_id"] for t in closed_cand]
        assert "TEST_001_legA" in setup_ids
        assert "TEST_001_legB" in setup_ids

        # Total lots must equal baseline lots (sum of legs)
        total_cand_lots = sum(t["lots"] for t in closed_cand)
        assert math.isclose(total_cand_lots, closed_base[0]["lots"], rel_tol=1e-5)
