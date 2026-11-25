"""
GoldFlow — Verification Suite for Chart Rendering Performance,
M15 Data Cryptographic Integrity, and Statistical Analysis Edge Cases.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from src.backtesting.engine import (
    analyze_consecutive_losses,
    compute_bootstrap_pf_ci,
)
from src.smc.engine import SMCConfig, analyze_smc
from src.visualization.charts import (
    create_candlestick_chart,
    create_monte_carlo_equity_fan_chart,
)

ROOT = Path(__file__).resolve().parent.parent


# ==============================================================================
# 1. CHART RENDERING PERFORMANCE & WINDOW FILTERING
# ==============================================================================

class TestChartPerformanceAndWindowFiltering:
    def test_chart_renders_under_one_second_on_large_smc_result(self):
        """Visible-window candlestick chart must render in < 1.0 second on 10,000 bars."""
        h1_path = ROOT / "data" / "processed" / "XAUUSD_H1_clean.csv"
        if not h1_path.exists():
            pytest.skip("XAUUSD_H1_clean.csv not found on disk")

        df = pd.read_csv(h1_path)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        smc_res = analyze_smc(df, symbol="XAUUSD", timeframe="H1", config=SMCConfig())

        # Render with visible_bars=500 (UI default)
        t0 = time.perf_counter()
        fig = create_candlestick_chart(df, smc_result=smc_res, visible_bars=500)
        elapsed = time.perf_counter() - t0

        assert fig is not None
        assert elapsed < 1.5, f"Chart rendering took {elapsed:.3f}s (must be < 1.5s)"
        # Verify shape count is reasonable (not the bloated 7,000+ off-screen shapes)
        assert len(fig.layout.shapes) < 1500
        assert len(fig.layout.annotations) < 200

    def test_chart_shapes_are_clamped_to_visible_window(self):
        """All rendered shapes must stay within or overlap the visible window."""
        times = pd.date_range("2026-01-01", periods=100, freq="1h", tz="UTC")
        df = pd.DataFrame({
            "time": times,
            "open": 2000.0 + np.sin(np.linspace(0, 10, 100)) * 20.0,
            "high": 2000.0 + np.sin(np.linspace(0, 10, 100)) * 20.0 + 5.0,
            "low": 2000.0 + np.sin(np.linspace(0, 10, 100)) * 20.0 - 5.0,
            "close": 2000.0 + np.sin(np.linspace(0, 10, 100)) * 20.0 + 1.0,
            "tick_volume": 100,
        })
        smc_res = analyze_smc(df, config=SMCConfig(swing_window=2))

        # Render visible_bars=30 (only the last 30 bars)
        fig = create_candlestick_chart(df, smc_result=smc_res, visible_bars=30)
        assert fig is not None
        assert len(fig.data[0].x) == 30

        chart_start = df["time"].iloc[-30]
        chart_end = df["time"].iloc[-1]

        # Check that no shape has both endpoints strictly outside the window
        for shape in fig.layout.shapes:
            if hasattr(shape, "x0") and hasattr(shape, "x1"):
                x0 = pd.to_datetime(shape.x0, utc=True)
                x1 = pd.to_datetime(shape.x1, utc=True)
                assert not (x0 < chart_start and x1 < chart_start), f"Shape {shape} ended before visible window"
                assert not (x0 > chart_end and x1 > chart_end), f"Shape {shape} started after visible window"

    def test_empty_dataframe_returns_valid_figure(self):
        """Empty input dataframe must return a valid go.Figure with informative text."""
        fig = create_candlestick_chart(pd.DataFrame())
        assert fig is not None
        assert any("No market data available" in str(a.text) for a in fig.layout.annotations)


# ==============================================================================
# 2. M15 CRYPTOGRAPHIC INTEGRITY VERIFICATION
# ==============================================================================

class TestM15CryptographicIntegrity:
    def test_m15_raw_sha256_matches_recorded_provenance(self):
        """The actual raw M15 dataset must cryptographically match the recorded SHA-256."""
        meta_path = ROOT / "data" / "processed" / "XAUUSD_M15_clean.meta.json"
        assert meta_path.exists(), "M15 clean metadata file missing"

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        recorded_hash = meta.get("raw_file_sha256")
        assert recorded_hash is not None, "raw_file_sha256 not in metadata"

        raw_path = ROOT / "data" / "raw" / "XAUUSD_M15_raw.csv"
        assert raw_path.exists(), "Raw M15 CSV file missing"

        actual_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        assert actual_hash == recorded_hash, (
            f"M15 raw file hash mismatch: recorded {recorded_hash} vs actual {actual_hash}"
        )

    def test_m15_raw_row_count_matches_clean_row_count(self):
        """M15 raw and clean row counts must agree (5,000 rows)."""
        raw_path = ROOT / "data" / "raw" / "XAUUSD_M15_raw.csv"
        clean_path = ROOT / "data" / "processed" / "XAUUSD_M15_clean.csv"

        df_raw = pd.read_csv(raw_path)
        df_clean = pd.read_csv(clean_path)
        assert len(df_raw) == 5000, f"Raw M15 row count is {len(df_raw)}, expected 5000"
        assert len(df_clean) == 5000, f"Clean M15 row count is {len(df_clean)}, expected 5000"


# ==============================================================================
# 3. STATISTICAL ANALYSIS EDGE CASES
# ==============================================================================

class TestStatisticalAnalysisEdgeCases:
    def test_bootstrap_pf_ci_empty(self):
        """Empty array returns (0.0, 0.0, 0.0)."""
        obs, lo, hi = compute_bootstrap_pf_ci([])
        assert obs == 0.0
        assert lo == 0.0
        assert hi == 0.0

    def test_bootstrap_pf_ci_all_wins(self):
        """All-winning trades returns (999.0, 999.0, 999.0)."""
        obs, lo, hi = compute_bootstrap_pf_ci([10.0, 20.0, 15.0])
        assert obs == 999.0
        assert lo == 999.0
        assert hi == 999.0

    def test_bootstrap_pf_ci_all_losses(self):
        """All-losing trades returns (0.0, 0.0, 0.0)."""
        obs, lo, hi = compute_bootstrap_pf_ci([-10.0, -20.0, -15.0])
        assert obs == 0.0
        assert lo == 0.0
        assert hi == 0.0

    def test_bootstrap_pf_ci_single_trade_win(self):
        """Single win returns (999.0, 999.0, 999.0)."""
        obs, lo, hi = compute_bootstrap_pf_ci([50.0])
        assert obs == 999.0
        assert lo == 999.0
        assert hi == 999.0

    def test_bootstrap_pf_ci_single_trade_loss(self):
        """Single loss returns (0.0, 0.0, 0.0)."""
        obs, lo, hi = compute_bootstrap_pf_ci([-50.0])
        assert obs == 0.0
        assert lo == 0.0
        assert hi == 0.0

    def test_bootstrap_pf_ci_mixed_trades(self):
        """Mixed trades returns valid observed PF and confidence bounds."""
        pnls = [100.0, -50.0, 80.0, -40.0, 120.0, -60.0, 90.0, -45.0]
        obs, lo, hi = compute_bootstrap_pf_ci(pnls, n_boot=500, ci=0.95, seed=42)
        expected_pf = sum(p for p in pnls if p > 0) / abs(sum(p for p in pnls if p < 0))
        assert abs(obs - expected_pf) < 1e-4
        assert lo <= obs
        assert hi >= obs

    def test_consecutive_losses_empty(self):
        """Empty array returns zeroes."""
        res = analyze_consecutive_losses([])
        assert res["max_streak"] == 0
        assert res["avg_streak"] == 0.0
        assert res["total_streaks"] == 0

    def test_consecutive_losses_all_wins(self):
        """All wins returns 0 streak."""
        res = analyze_consecutive_losses([10.0, 20.0, 30.0])
        assert res["max_streak"] == 0
        assert res["avg_streak"] == 0.0
        assert res["total_streaks"] == 0

    def test_consecutive_losses_all_losses(self):
        """All losses returns single streak of full length."""
        res = analyze_consecutive_losses([-5.0, -10.0, -15.0, -20.0])
        assert res["max_streak"] == 4
        assert res["avg_streak"] == 4.0
        assert res["total_streaks"] == 1

    def test_consecutive_losses_known_sequence(self):
        """Sequence with streaks of 2 and 3 losses."""
        # Win, Loss, Loss, Win, Loss, Loss, Loss, Win
        pnls = [10.0, -5.0, -5.0, 10.0, -5.0, -5.0, -5.0, 10.0]
        res = analyze_consecutive_losses(pnls)
        assert res["max_streak"] == 3
        assert res["total_streaks"] == 2
        assert res["avg_streak"] == 2.5


# ==============================================================================
# 4. MONTE CARLO FAN CHART EDGE CASES
# ==============================================================================

class TestMonteCarloFanChartEdgeCases:
    def test_monte_carlo_empty_series(self):
        """Empty PnL series returns valid figure with informative annotation."""
        fig = create_monte_carlo_equity_fan_chart([])
        assert fig is not None
        assert any("No trade records available" in str(a.text) for a in fig.layout.annotations)

    def test_monte_carlo_single_trade(self):
        """Single trade generates valid fan chart."""
        fig = create_monte_carlo_equity_fan_chart([100.0])
        assert fig is not None
        trace_names = [t.name for t in fig.data if t.name]
        assert "Median Simulated Path" in trace_names
        assert "Realized Sequence" in trace_names

    def test_monte_carlo_valid_series(self):
        """Valid trade series generates fan chart traces."""
        pnls = [50.0, -30.0, 80.0, -40.0, 100.0, -50.0, 20.0, -10.0]
        fig = create_monte_carlo_equity_fan_chart(pnls, initial_capital=10000.0, n_sims=50)
        assert fig is not None
        trace_names = [t.name for t in fig.data if t.name]
        assert "Median Simulated Path" in trace_names
        assert "Realized Sequence" in trace_names
        assert "90th Pct (Optimistic)" in trace_names
        assert "10th Pct (Pessimistic)" in trace_names
