from dataclasses import asdict

import pandas as pd
import pytest

from scripts.run_smc_validation import (
    _scaled_cost_inputs,
    chronological_split_index,
    filter_candidates_from_index,
)
from src.backtesting.engine import BacktestConfig


def test_chronological_split_uses_floor_and_keeps_both_partitions():
    assert chronological_split_index(10, 0.70) == 7
    assert chronological_split_index(11, 0.70) == 7
    with pytest.raises(ValueError, match="At least 3 bars"):
        chronological_split_index(2)
    with pytest.raises(ValueError, match="train_fraction"):
        chronological_split_index(10, 1.0)


def test_holdout_filter_only_keeps_signals_on_or_after_boundary():
    candidates = [
        {"setup_id": "before", "signal_index": 4},
        {"setup_id": "boundary", "signal_index": 5},
        {"setup_id": "after", "signal_index": 7},
    ]
    assert [c["setup_id"] for c in filter_candidates_from_index(candidates, 5)] == ["boundary", "after"]
    with pytest.raises(ValueError, match="signal_index"):
        filter_candidates_from_index([{"setup_id": "missing"}], 5)


def test_cost_stress_scales_spread_slippage_fallback_and_commission():
    frame = pd.DataFrame({"time": pd.date_range("2026-01-01", periods=2, tz="UTC"), "spread": [10, 20]})
    config = BacktestConfig(fallback_spread_usd=0.2, slippage_per_side_usd=0.05, commission_per_lot_per_side=2.0)
    scaled_frame, scaled_config = _scaled_cost_inputs(frame, config, 2.0)
    assert scaled_frame["spread"].tolist() == [20, 40]
    assert scaled_config.fallback_spread_usd == pytest.approx(0.4)
    assert scaled_config.slippage_per_side_usd == pytest.approx(0.1)
    assert scaled_config.commission_per_lot_per_side == pytest.approx(4.0)
    assert asdict(config)["fallback_spread_usd"] == pytest.approx(0.2)  # immutable base is unchanged


def test_holdout_candidate_indices_are_temporal_not_candidate_order_dependent():
    candidates = [
        {"signal_index": 15, "signal_time": "2026-02-01T00:00:00Z"},
        {"signal_index": 3, "signal_time": "2026-01-01T00:00:00Z"},
        {"signal_index": 10, "signal_time": "2026-01-20T00:00:00Z"},
    ]
    selected = filter_candidates_from_index(candidates, 10)
    assert [c["signal_index"] for c in selected] == [15, 10]
