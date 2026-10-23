"""Phase 4.1 Cost Regression Tests.

Validates:
  - Experiment A: fixed-size cost replay is monotonic (higher costs -> worse net P&L)
  - Frozen lot sizes are never silently recalculated during replay
  - Gross P&L is scenario-independent on a frozen ledger
  - Commission is charged exactly once round-trip
  - Slippage is 2-sided for STOP_LOSS, 1-sided for TAKE_PROFIT
  - net P&L == raw_gross - (spread + slippage + commission) to floating-point precision
  - spread_multiplier is applied to bar-level and fallback spread in run_event_backtest
  - Increasing spread_multiplier changes net P&L in the expected (worse) direction
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.backtesting.engine import BacktestConfig, replay_trade_ledger_costs, run_event_backtest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _settled_trades():
    """Minimal 2-trade closed ledger for Experiment A replay tests."""
    return [
        {
            "status": "CLOSED",
            "side": "LONG",
            "lots": 0.10,
            "raw_gross_pnl": 100.0,
            "estimated_stop_risk_cash": 50.0,
            "exit_reason": "STOP_LOSS",       # 2-sided slippage
            "entry_spread_usd": 0.20,
            "exit_spread_usd": 0.20,
        },
        {
            "status": "CLOSED",
            "side": "LONG",
            "lots": 0.05,
            "raw_gross_pnl": -60.0,
            "estimated_stop_risk_cash": 30.0,
            "exit_reason": "TAKE_PROFIT",     # 1-sided slippage (entry only)
            "entry_spread_usd": 0.20,
            "exit_spread_usd": 0.20,
        },
    ]


def _single_trade(exit_reason="STOP_LOSS", lots=0.10, gross=50.0):
    return [
        {
            "status": "CLOSED",
            "side": "LONG",
            "lots": lots,
            "raw_gross_pnl": gross,
            "estimated_stop_risk_cash": abs(gross) * 0.5,
            "exit_reason": exit_reason,
            "entry_spread_usd": 0.20,
            "exit_spread_usd": 0.20,
        }
    ]


# ---------------------------------------------------------------------------
# Experiment A — Fixed-size cost replay monotonicity
# ---------------------------------------------------------------------------

class TestExperimentAMonotonicity:
    """Higher costs on a frozen ledger can never improve net P&L."""

    def test_higher_spread_multiplier_increases_spread_cost_and_reduces_net(self):
        t = _settled_trades()
        r1 = replay_trade_ledger_costs(t, spread_multiplier=1.0, slippage_per_side_usd=0.05,
                                        commission_per_lot_per_side=0.0)
        r2 = replay_trade_ledger_costs(t, spread_multiplier=2.0, slippage_per_side_usd=0.05,
                                        commission_per_lot_per_side=0.0)
        assert r2["total_spread_cost"] > r1["total_spread_cost"], (
            "Doubling spread_multiplier must increase total_spread_cost"
        )
        assert r2["net_profit"] < r1["net_profit"], (
            "Doubling spread_multiplier must reduce net_profit on a fixed ledger"
        )

    def test_3x_spread_worse_than_2x(self):
        t = _settled_trades()
        r2 = replay_trade_ledger_costs(t, spread_multiplier=2.0, slippage_per_side_usd=0.05,
                                        commission_per_lot_per_side=0.0)
        r3 = replay_trade_ledger_costs(t, spread_multiplier=3.0, slippage_per_side_usd=0.05,
                                        commission_per_lot_per_side=0.0)
        assert r3["total_spread_cost"] > r2["total_spread_cost"]
        assert r3["net_profit"] < r2["net_profit"]

    def test_higher_slippage_increases_slippage_cost_and_reduces_net(self):
        t = _settled_trades()
        r1 = replay_trade_ledger_costs(t, spread_multiplier=1.0, slippage_per_side_usd=0.05,
                                        commission_per_lot_per_side=0.0)
        r2 = replay_trade_ledger_costs(t, spread_multiplier=1.0, slippage_per_side_usd=0.10,
                                        commission_per_lot_per_side=0.0)
        assert r2["total_slippage_cost"] > r1["total_slippage_cost"]
        assert r2["net_profit"] < r1["net_profit"]

    def test_adding_commission_increases_costs_and_reduces_net(self):
        t = _settled_trades()
        r0 = replay_trade_ledger_costs(t, spread_multiplier=1.0, slippage_per_side_usd=0.05,
                                        commission_per_lot_per_side=0.0)
        r1 = replay_trade_ledger_costs(t, spread_multiplier=1.0, slippage_per_side_usd=0.05,
                                        commission_per_lot_per_side=1.0)
        assert r1["total_commission"] > r0["total_commission"]
        assert r1["net_profit"] < r0["net_profit"]

    def test_worst_case_highest_total_costs_lowest_net(self):
        t = _settled_trades()
        r_base = replay_trade_ledger_costs(t, spread_multiplier=1.0,
                                            slippage_per_side_usd=0.05,
                                            commission_per_lot_per_side=0.0)
        r_worst = replay_trade_ledger_costs(t, spread_multiplier=3.0,
                                             slippage_per_side_usd=0.20,
                                             commission_per_lot_per_side=2.0)
        assert r_worst["total_transaction_costs"] > r_base["total_transaction_costs"]
        assert r_worst["net_profit"] < r_base["net_profit"]


class TestExperimentAGrossFreeze:
    """Raw gross P&L is scenario-independent on a frozen trade ledger."""

    @pytest.mark.parametrize("mult,slip,comm", [
        (1.0, 0.05, 0.0),
        (2.0, 0.05, 0.0),
        (3.0, 0.05, 0.0),
        (1.0, 0.10, 0.0),
        (2.0, 0.20, 2.0),
        (3.0, 0.20, 2.0),
    ])
    def test_raw_gross_unchanged(self, mult, slip, comm):
        t = _settled_trades()
        expected = sum(tr["raw_gross_pnl"] for tr in t)
        r = replay_trade_ledger_costs(t, spread_multiplier=mult,
                                       slippage_per_side_usd=slip,
                                       commission_per_lot_per_side=comm)
        assert abs(r["total_raw_gross_profit"] - expected) < 1e-6, (
            f"raw_gross changed under mult={mult} slip={slip} comm={comm}"
        )

    def test_net_equals_gross_minus_total_costs(self):
        t = _settled_trades()
        r = replay_trade_ledger_costs(t, spread_multiplier=2.0,
                                       slippage_per_side_usd=0.10,
                                       commission_per_lot_per_side=1.0)
        expected_net = r["total_raw_gross_profit"] - r["total_transaction_costs"]
        assert abs(r["net_profit"] - expected_net) < 1e-6, (
            f"net_profit={r['net_profit']:.6f} != gross - costs={expected_net:.6f}"
        )


class TestExperimentACostConventions:
    """Commission and slippage conventions are applied correctly."""

    def test_commission_charged_exactly_round_trip(self):
        """Commission = 2 * commission_per_lot * lots (round trip)."""
        lots = 0.10
        t = _single_trade(lots=lots)
        r = replay_trade_ledger_costs(t, spread_multiplier=1.0, slippage_per_side_usd=0.0,
                                       commission_per_lot_per_side=3.0, contract_size_oz=100.0)
        expected = 2.0 * 3.0 * lots
        assert abs(r["total_commission"] - expected) < 1e-6, (
            f"Expected round-trip commission {expected:.4f}, got {r['total_commission']:.4f}"
        )

    def test_slippage_two_sided_for_stop_loss(self):
        """STOP_LOSS exit should incur entry + exit slippage."""
        t = _single_trade(exit_reason="STOP_LOSS", lots=0.10)
        r = replay_trade_ledger_costs(t, spread_multiplier=1.0, slippage_per_side_usd=0.10,
                                       commission_per_lot_per_side=0.0, contract_size_oz=100.0)
        # 2 sides: 0.10 * 2 * 100 * 0.10 = 2.00 USD
        assert r["total_slippage_cost"] == pytest.approx(2.0 * 0.10 * 100.0 * 0.10, rel=1e-6)

    def test_slippage_one_sided_for_take_profit(self):
        """TAKE_PROFIT exit incurs slippage on entry side only."""
        t_sl = _single_trade(exit_reason="STOP_LOSS", lots=0.10)
        t_tp = _single_trade(exit_reason="TAKE_PROFIT", lots=0.10)
        r_sl = replay_trade_ledger_costs(t_sl, spread_multiplier=1.0, slippage_per_side_usd=0.10,
                                          commission_per_lot_per_side=0.0, contract_size_oz=100.0)
        r_tp = replay_trade_ledger_costs(t_tp, spread_multiplier=1.0, slippage_per_side_usd=0.10,
                                          commission_per_lot_per_side=0.0, contract_size_oz=100.0)
        assert r_sl["total_slippage_cost"] == pytest.approx(r_tp["total_slippage_cost"] * 2, rel=1e-6), (
            "STOP_LOSS must charge exactly 2x the slippage of TAKE_PROFIT for the same lots"
        )

    def test_commission_applied_once_not_twice_per_scenario_call(self):
        """A single call to replay_trade_ledger_costs does not double-count commission."""
        lots = 0.05
        t = _single_trade(lots=lots)
        r = replay_trade_ledger_costs(t, spread_multiplier=1.0, slippage_per_side_usd=0.0,
                                       commission_per_lot_per_side=2.0, contract_size_oz=100.0)
        # Round-trip = 2 * 2.0 * 0.05 = 0.20
        assert abs(r["total_commission"] - 0.20) < 1e-6


class TestExperimentALotSizeFreeze:
    """Frozen lot sizes must not be silently recalculated during replay."""

    def test_replay_preserves_lots_exactly(self):
        original_lots = 0.07
        t = _single_trade(lots=original_lots)
        for mult in [1.0, 2.0, 3.0]:
            r = replay_trade_ledger_costs(t, spread_multiplier=mult,
                                           slippage_per_side_usd=0.05,
                                           commission_per_lot_per_side=0.0)
            assert r["trades"][0]["lots"] == pytest.approx(original_lots), (
                f"Lots changed at spread_multiplier={mult}: {r['trades'][0]['lots']}"
            )

    def test_replay_raw_gross_same_as_original(self):
        """Raw gross must match the trade's own raw_gross_pnl, not be recomputed."""
        gross = -99.75
        t = _single_trade(lots=0.07, gross=gross)
        for mult, slip, comm in [(1.0, 0.05, 0.0), (2.0, 0.10, 0.0), (3.0, 0.20, 2.0)]:
            r = replay_trade_ledger_costs(t, spread_multiplier=mult,
                                           slippage_per_side_usd=slip,
                                           commission_per_lot_per_side=comm)
            assert abs(r["total_raw_gross_profit"] - gross) < 1e-6

    def test_skipped_trades_not_counted_in_costs(self):
        trades = [
            {"status": "SKIPPED", "skip_reason": "max_concurrent_positions"},
            {
                "status": "CLOSED", "side": "LONG", "lots": 0.05,
                "raw_gross_pnl": 20.0, "estimated_stop_risk_cash": 10.0,
                "exit_reason": "STOP_LOSS",
                "entry_spread_usd": 0.20, "exit_spread_usd": 0.20,
            },
        ]
        r = replay_trade_ledger_costs(trades, spread_multiplier=2.0,
                                       slippage_per_side_usd=0.10,
                                       commission_per_lot_per_side=1.0)
        assert r["total_trades"] == 1, "Only CLOSED trades should be counted"
        assert r["total_raw_gross_profit"] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Spread multiplier wiring in the full engine (§4 anomaly proof)
# ---------------------------------------------------------------------------

class TestSpreadMultiplierWiringInEngine:
    """Prove that spread_multiplier in BacktestConfig reaches every fill calculation.

    This guards against the previously observed anomaly where 2x/3x_spread
    scenarios left H4, M15, M5 net P&L completely unchanged because the
    spread_multiplier was not applied to bar-level spread data.
    """

    def _bar_frame(self, with_spread_col: bool = True, spread_pts: int = 20):
        rows = [
            {"time": pd.Timestamp("2026-01-01T00:00:00Z"), "open": 2000.0,
             "high": 2001.0, "low": 1999.0, "close": 2000.0},
            {"time": pd.Timestamp("2026-01-01T01:00:00Z"), "open": 2000.0,
             "high": 2001.0, "low": 1999.0, "close": 2000.0},
            {"time": pd.Timestamp("2026-01-01T02:00:00Z"), "open": 1988.0,
             "high": 1988.5, "low": 1985.0, "close": 1985.0},
        ]
        if with_spread_col:
            for r in rows:
                r["spread"] = spread_pts
        return pd.DataFrame(rows)

    def _cand(self):
        return {
            "setup_id": "SPREAD_MULT_PROOF",
            "signal_index": 0,
            "signal_time": pd.Timestamp("2026-01-01T00:00:00Z").isoformat(),
            "direction": "BULLISH",
            "stop_loss_reference": 1990.0,
            "take_profit_reference": 2020.0,
            "target_source": "test",
        }

    def test_2x_spread_multiplier_reduces_net_pnl_with_bar_spread(self):
        """With a bar spread column present, spread_multiplier must scale the spread."""
        frame = self._bar_frame(with_spread_col=True, spread_pts=20)
        cfg1 = BacktestConfig(spread_multiplier=1.0, slippage_per_side_usd=0.0,
                               commission_per_lot_per_side=0.0)
        cfg2 = BacktestConfig(spread_multiplier=2.0, slippage_per_side_usd=0.0,
                               commission_per_lot_per_side=0.0)
        r1 = run_event_backtest(frame, [self._cand()], cfg1)
        r2 = run_event_backtest(frame, [self._cand()], cfg2)
        c1 = [t for t in r1.trades if t.get("status") == "CLOSED"]
        c2 = [t for t in r2.trades if t.get("status") == "CLOSED"]
        assert c1 and c2, "Expected a closed trade for both spread_multiplier values"
        assert c2[0]["net_pnl"] < c1[0]["net_pnl"], (
            f"2x spread_multiplier must reduce net_pnl; "
            f"got 1x={c1[0]['net_pnl']:.4f} 2x={c2[0]['net_pnl']:.4f}"
        )

    def test_entry_spread_usd_doubles_when_multiplier_doubles_bar_spread(self):
        frame = self._bar_frame(with_spread_col=True, spread_pts=20)
        cfg1 = BacktestConfig(spread_multiplier=1.0, slippage_per_side_usd=0.0,
                               commission_per_lot_per_side=0.0)
        cfg2 = BacktestConfig(spread_multiplier=2.0, slippage_per_side_usd=0.0,
                               commission_per_lot_per_side=0.0)
        r1 = run_event_backtest(frame, [self._cand()], cfg1)
        r2 = run_event_backtest(frame, [self._cand()], cfg2)
        c1 = [t for t in r1.trades if t.get("status") == "CLOSED"]
        c2 = [t for t in r2.trades if t.get("status") == "CLOSED"]
        if c1 and c2:
            assert c2[0]["entry_spread_usd"] == pytest.approx(
                c1[0]["entry_spread_usd"] * 2, rel=1e-6
            ), (
                f"entry_spread_usd must double; "
                f"got 1x={c1[0]['entry_spread_usd']:.4f} 2x={c2[0]['entry_spread_usd']:.4f}"
            )

    def test_2x_spread_multiplier_reduces_net_pnl_with_fallback_only(self):
        """Without a bar spread column, fallback_spread_usd must still be multiplied."""
        frame = self._bar_frame(with_spread_col=False)
        cfg1 = BacktestConfig(spread_multiplier=1.0, fallback_spread_usd=0.20,
                               slippage_per_side_usd=0.0, commission_per_lot_per_side=0.0)
        cfg2 = BacktestConfig(spread_multiplier=2.0, fallback_spread_usd=0.20,
                               slippage_per_side_usd=0.0, commission_per_lot_per_side=0.0)
        r1 = run_event_backtest(frame, [self._cand()], cfg1)
        r2 = run_event_backtest(frame, [self._cand()], cfg2)
        c1 = [t for t in r1.trades if t.get("status") == "CLOSED"]
        c2 = [t for t in r2.trades if t.get("status") == "CLOSED"]
        if c1 and c2:
            assert c2[0]["entry_spread_usd"] == pytest.approx(
                c1[0]["entry_spread_usd"] * 2, rel=1e-6
            )

    def test_non_negative_spread_cost_with_positive_spread(self):
        """Spread cost recorded in the trade must be >= 0 whenever spread > 0."""
        frame = self._bar_frame(with_spread_col=True, spread_pts=10)
        cfg = BacktestConfig(spread_multiplier=1.0, slippage_per_side_usd=0.0,
                              commission_per_lot_per_side=0.0)
        r = run_event_backtest(frame, [self._cand()], cfg)
        for t in r.trades:
            if t.get("status") == "CLOSED":
                assert t["spread_cost"] >= 0.0, f"Negative spread_cost: {t['spread_cost']}"

    def test_spread_cost_increases_with_lots(self):
        """For a fixed spread, larger lot size must produce a proportionally larger spread cost."""
        frame = self._bar_frame(with_spread_col=True, spread_pts=20)
        # Large capital gives more lots
        cfg_small = BacktestConfig(initial_capital=1_000.0, spread_multiplier=1.0,
                                    slippage_per_side_usd=0.0, commission_per_lot_per_side=0.0)
        cfg_large = BacktestConfig(initial_capital=100_000.0, spread_multiplier=1.0,
                                    slippage_per_side_usd=0.0, commission_per_lot_per_side=0.0)
        r_small = run_event_backtest(frame, [self._cand()], cfg_small)
        r_large = run_event_backtest(frame, [self._cand()], cfg_large)
        c_small = [t for t in r_small.trades if t.get("status") == "CLOSED"]
        c_large = [t for t in r_large.trades if t.get("status") == "CLOSED"]
        if c_small and c_large and c_large[0]["lots"] > c_small[0]["lots"]:
            assert c_large[0]["spread_cost"] > c_small[0]["spread_cost"], (
                "More lots must produce larger spread_cost at same spread"
            )
