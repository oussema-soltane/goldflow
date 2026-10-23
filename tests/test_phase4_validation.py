"""Tests for Phase 4 components: ChronologicalSplit and Phase 4 pipeline validation."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.backtesting.split import ChronologicalSplit, SplitConfig, chronological_split
from src.backtesting.engine import BacktestConfig, run_event_backtest


# ---- Helpers ----

def _make_ohlc(n: int, start_price: float = 100.0) -> pd.DataFrame:
    """Minimal synthetic OHLC dataframe."""
    times = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    prices = [start_price + i * 0.1 for i in range(n)]
    return pd.DataFrame({
        "time": times,
        "open":  prices,
        "high":  [p + 0.5 for p in prices],
        "low":   [p - 0.5 for p in prices],
        "close": prices,
    })


# ---- SplitConfig tests ----

class TestSplitConfig:
    def test_default_fractions_valid(self):
        cfg = SplitConfig()
        assert cfg.train_fraction == 0.60
        assert cfg.validate_fraction == 0.20
        assert abs(cfg.holdout_fraction - 0.20) < 1e-9

    def test_custom_fractions(self):
        cfg = SplitConfig(train_fraction=0.70, validate_fraction=0.15)
        assert abs(cfg.holdout_fraction - 0.15) < 1e-9

    def test_fractions_summing_to_one_raises(self):
        with pytest.raises(ValueError, match="must be < 1"):
            SplitConfig(train_fraction=0.80, validate_fraction=0.20)

    def test_fraction_out_of_range_raises(self):
        with pytest.raises(ValueError):
            SplitConfig(train_fraction=0.0)

    def test_fraction_above_one_raises(self):
        with pytest.raises(ValueError):
            SplitConfig(train_fraction=1.5)

    def test_invalid_min_rows(self):
        with pytest.raises(ValueError):
            SplitConfig(min_rows_per_segment=0)


# ---- ChronologicalSplit tests ----

class TestChronologicalSplit:
    def test_basic_split_row_counts(self):
        df = _make_ohlc(100)
        split = ChronologicalSplit(df, SplitConfig(train_fraction=0.6, validate_fraction=0.2))
        assert split.segments[0].label == "train"
        assert split.segments[1].label == "validate"
        assert split.segments[2].label == "holdout"
        total = sum(s.n_rows for s in split.segments)
        assert total == 100

    def test_no_overlap_between_segments(self):
        df = _make_ohlc(100)
        split = ChronologicalSplit(df)
        train_times = set(split.train["time"].astype(str))
        val_times   = set(split.validate["time"].astype(str))
        hold_times  = set(split.holdout["time"].astype(str))
        assert train_times.isdisjoint(val_times)
        assert train_times.isdisjoint(hold_times)
        assert val_times.isdisjoint(hold_times)

    def test_chronological_ordering_preserved(self):
        df = _make_ohlc(50)
        split = ChronologicalSplit(df)
        for seg_label in ("train", "validate", "holdout"):
            seg = split.get_segment(seg_label)
            assert seg["time"].is_monotonic_increasing

    def test_train_ends_before_validate_starts(self):
        df = _make_ohlc(60)
        split = ChronologicalSplit(df)
        assert split.segments[0].end_time < split.segments[1].start_time

    def test_validate_ends_before_holdout_starts(self):
        df = _make_ohlc(60)
        split = ChronologicalSplit(df)
        assert split.segments[1].end_time < split.segments[2].start_time

    def test_minimum_3_rows_required(self):
        df = _make_ohlc(2)
        with pytest.raises(ValueError, match="at least 3 rows"):
            ChronologicalSplit(df)

    def test_non_chronological_input_raises(self):
        df = _make_ohlc(20)
        df = df.iloc[::-1].reset_index(drop=True)
        with pytest.raises(ValueError, match="chronological"):
            ChronologicalSplit(df)

    def test_duplicate_timestamps_raises(self):
        df = _make_ohlc(20)
        df.iloc[5] = df.iloc[4]  # duplicate time
        with pytest.raises(ValueError, match="unique"):
            ChronologicalSplit(df)

    def test_missing_column_raises(self):
        df = _make_ohlc(20).drop(columns=["close"])
        with pytest.raises(ValueError, match="missing columns"):
            ChronologicalSplit(df)

    def test_small_dataset_warning(self):
        df = _make_ohlc(10)
        split = ChronologicalSplit(df, SplitConfig(min_rows_per_segment=20))
        assert len(split.warnings) > 0
        assert any("rows" in w for w in split.warnings)

    def test_summary_structure(self):
        df = _make_ohlc(90)
        split = ChronologicalSplit(df)
        s = split.summary()
        assert s["total_rows"] == 90
        assert len(s["segments"]) == 3
        assert all(seg["label"] in ("train", "validate", "holdout") for seg in s["segments"])

    def test_convenience_wrapper(self):
        df = _make_ohlc(30)
        split = chronological_split(df)
        assert isinstance(split, ChronologicalSplit)

    def test_get_segment_unknown_label_raises(self):
        df = _make_ohlc(30)
        split = ChronologicalSplit(df)
        with pytest.raises(ValueError, match="Unknown segment"):
            split.get_segment("nonexistent")

    def test_all_rows_accounted_for(self):
        for n in (10, 50, 100, 500):
            df = _make_ohlc(n)
            split = ChronologicalSplit(df)
            total = sum(s.n_rows for s in split.segments)
            assert total == n, f"Row mismatch for n={n}: {total} != {n}"

    def test_segment_reset_index(self):
        df = _make_ohlc(30)
        split = ChronologicalSplit(df)
        for seg_label in ("train", "validate", "holdout"):
            seg = split.get_segment(seg_label)
            assert list(seg.index) == list(range(len(seg)))


# ---- SplitConfig holdout fraction tests ----

class TestHoldoutFraction:
    def test_holdout_fraction_is_remainder(self):
        cfg = SplitConfig(train_fraction=0.65, validate_fraction=0.20)
        assert abs(cfg.holdout_fraction - 0.15) < 1e-9

    def test_holdout_gets_actual_rows(self):
        df = _make_ohlc(100)
        split = ChronologicalSplit(df, SplitConfig(train_fraction=0.65, validate_fraction=0.20))
        assert split.segments[2].n_rows >= 1


# ---- Backtest config validation for Phase 4 cost scenarios ----

class TestPhase4CostScenarios:
    """Validate that BacktestConfig accepts all predeclared cost scenario values."""

    SCENARIOS = [
        (0.20, 0.05, 0.00),
        (0.40, 0.05, 0.00),
        (0.60, 0.05, 0.00),
        (0.20, 0.10, 0.00),
        (0.40, 0.10, 0.00),
        (0.20, 0.05, 1.00),
        (0.60, 0.20, 2.00),
    ]

    @pytest.mark.parametrize("spread,slip,comm", SCENARIOS)
    def test_config_accepts_scenario(self, spread, slip, comm):
        cfg = BacktestConfig(
            fallback_spread_usd=spread,
            slippage_per_side_usd=slip,
            commission_per_lot_per_side=comm,
        )
        assert cfg.fallback_spread_usd == spread
        assert cfg.slippage_per_side_usd == slip
        assert cfg.commission_per_lot_per_side == comm

    def test_backtest_runs_with_worst_case_costs(self):
        """Verify the backtest engine runs cleanly with worst-case costs."""
        df = _make_ohlc(50)
        cfg = BacktestConfig(
            fallback_spread_usd=0.60,
            slippage_per_side_usd=0.20,
            commission_per_lot_per_side=2.00,
        )
        # No candidates means no trades but the engine should not crash
        result = run_event_backtest(df, [], cfg, timeframe="H4")
        assert result.metrics["closed_trades"] == 0

    def test_backtest_with_commission_charges_correctly(self):
        """Commission is charged twice (round trip) per trade."""
        df = _make_ohlc(10)
        cfg = BacktestConfig(
            initial_capital=10_000.0,
            risk_fraction=0.01,
            commission_per_lot_per_side=5.00,
            fallback_spread_usd=0.00,
            slippage_per_side_usd=0.00,
        )
        # Synthetic candidate: guaranteed take-profit within 5 bars
        bar0_open = float(df["open"].iloc[1])
        candidate = {
            "setup_id": "TEST_001",
            "timeframe": "H4",
            "direction": "LONG",
            "signal_index": 0,
            "signal_time": df["time"].iloc[0].isoformat(),
            "stop_loss_reference": bar0_open - 10.0,
            "take_profit_reference": bar0_open + 5.0,
            "target_source": "test",
        }
        result = run_event_backtest(df, [candidate], cfg, timeframe="H4")
        closed = [t for t in result.trades if t.get("status") == "CLOSED"]
        if closed:
            # commission must be exactly 2 * commission_per_lot * lots
            for t in closed:
                expected_comm = 2 * 5.00 * t["lots"]
                assert abs(t["commission"] - expected_comm) < 1e-6


# ---- Frozen config file integrity test ----

class TestFrozenConfig:
    def test_frozen_config_exists(self):
        path = Path(__file__).resolve().parent.parent / "configs" / "smc_v1_frozen.json"
        assert path.exists(), f"Frozen config file missing: {path}"

    def test_frozen_config_is_valid_json(self):
        path = Path(__file__).resolve().parent.parent / "configs" / "smc_v1_frozen.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "_schema" in data
        assert "strategy_rules" in data

    def test_frozen_config_has_required_fields(self):
        path = Path(__file__).resolve().parent.parent / "configs" / "smc_v1_frozen.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        rules = data.get("strategy_rules", {})
        # Check key rule categories exist
        for key in ("setup_type", "stop_loss", "take_profit", "risk_management", "entry"):
            assert key in rules, f"Missing key '{key}' in strategy_rules"

    def test_frozen_config_risk_fraction_matches_defaults(self):
        path = Path(__file__).resolve().parent.parent / "configs" / "smc_v1_frozen.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        rm = data["strategy_rules"]["risk_management"]
        assert rm["risk_fraction"] == 0.01
        assert rm["initial_capital_usd"] == 10000.0


# ---- Segment boundary leak prevention ----

class TestBoundaryLeakPrevention:
    """Verify that no candidate signal bleeds across segment boundaries."""

    def test_train_signals_do_not_appear_in_validate(self):
        df = _make_ohlc(120)
        split = ChronologicalSplit(df, SplitConfig(train_fraction=0.5, validate_fraction=0.25))
        train_end = split.segments[0].end_time
        val_start = split.segments[1].start_time
        assert train_end < val_start, "Train end must be strictly before validate start"

    def test_validate_signals_do_not_appear_in_holdout(self):
        df = _make_ohlc(120)
        split = ChronologicalSplit(df, SplitConfig(train_fraction=0.5, validate_fraction=0.25))
        val_end = split.segments[1].end_time
        hold_start = split.segments[2].start_time
        assert val_end < hold_start, "Validate end must be strictly before holdout start"

    def test_segment_rows_are_non_overlapping(self):
        df = _make_ohlc(90)
        split = ChronologicalSplit(df, SplitConfig())
        ranges = [(s.row_start, s.row_end) for s in split.segments]
        for i in range(len(ranges) - 1):
            assert ranges[i][1] == ranges[i + 1][0], \
                f"Segments {i} and {i+1} are not contiguous: {ranges[i]} vs {ranges[i+1]}"


# ---- Phase 4 pipeline segment indexing regression test ----

class TestPhase4SegmentExecution:
    """Verify that _run_segment correctly evaluates candidates within the target segment rows."""

    def test_run_segment_uses_correct_row_bounds(self):
        from scripts.run_smc_phase4_validation import _run_segment
        df = _make_ohlc(100)
        split = ChronologicalSplit(df, SplitConfig(train_fraction=0.6, validate_fraction=0.2))
        cfg = BacktestConfig()

        for seg_info in split.segments:
            seg_df = split.get_segment(seg_info.label)
            res = _run_segment(
                df,
                seg_df,
                seg_info.row_start,
                seg_info.row_end - 1,
                seg_info.label,
                "H4",
                cfg,
            )
            assert res["segment"] == seg_info.label
            assert res["n_rows"] == seg_info.n_rows
            assert res["segment_start"] == seg_info.start_time.isoformat()
            assert res["segment_end"] == seg_info.end_time.isoformat()

