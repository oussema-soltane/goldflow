"""
Tests for Phase 6F UI Redesign and Advanced Financial Visualization Components.

Verifies candlestick charting, overlay visibility, visible bar slicing, trade execution markers,
dealing range boundaries, equity curves, drawdown calculations, and distribution plots.
"""

from __future__ import annotations

import datetime as dt
import pandas as pd
import pytest

from src.data.loader import generate_synthetic_gold_data
from src.smc.engine import analyze_smc
from src.visualization.charts import (
    create_candlestick_chart,
    create_equity_curve_chart,
    create_performance_by_session_chart,
    create_pnl_distribution_chart,
    create_trade_outcome_donut,
)


class TestUIRedesignComponents:
    """Test suite for professional UI visualization components."""

    @pytest.fixture
    def sample_bars(self) -> pd.DataFrame:
        df, _ = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="M15", n_bars=150, seed=42)
        return df

    @pytest.fixture
    def sample_trades(self, sample_bars: pd.DataFrame) -> pd.DataFrame:
        t0 = sample_bars["time"].iloc[20]
        t1 = sample_bars["time"].iloc[40]
        t2 = sample_bars["time"].iloc[60]
        t3 = sample_bars["time"].iloc[80]

        return pd.DataFrame([
            {
                "setup_id": "TRADE_01",
                "side": "LONG",
                "entry_time": t0,
                "entry_price": 2650.0,
                "exit_time": t1,
                "exit_price": 2665.0,
                "stop_loss": 2640.0,
                "take_profit": 2670.0,
                "lots": 0.5,
                "net_pnl": 75.0,
                "R_multiple": 1.5,
                "exit_reason": "TAKE_PROFIT",
                "bars_held": 20,
            },
            {
                "setup_id": "TRADE_02",
                "side": "SHORT",
                "entry_time": t2,
                "entry_price": 2660.0,
                "exit_time": t3,
                "exit_price": 2670.0,
                "stop_loss": 2670.0,
                "take_profit": 2640.0,
                "lots": 0.5,
                "net_pnl": -50.0,
                "R_multiple": -1.0,
                "exit_reason": "STOP_LOSS",
                "bars_held": 20,
            },
        ])

    def test_visible_bars_slicing(self, sample_bars: pd.DataFrame):
        """Slicing visible_bars restricts candles while preserving valid Plotly figure."""
        fig_50 = create_candlestick_chart(sample_bars, visible_bars=50)
        assert fig_50 is not None
        candle_trace = fig_50.data[0]
        assert len(candle_trace.x) == 50

        # All bars when visible_bars is None
        fig_all = create_candlestick_chart(sample_bars, visible_bars=None)
        assert len(fig_all.data[0].x) == len(sample_bars)

    def test_trade_overlay_markers_rendered(self, sample_bars: pd.DataFrame, sample_trades: pd.DataFrame):
        """Passing trades renders Long entry, Short entry, and exit markers."""
        fig = create_candlestick_chart(
            sample_bars,
            trades=sample_trades,
            show_trades=True,
        )
        trace_names = [t.name for t in fig.data if t.name]
        assert "Trade Entry (Long)" in trace_names
        assert "Trade Entry (Short)" in trace_names
        assert "Exit (Profit)" in trace_names
        assert "Exit (Loss)" in trace_names

        # Verify shapes for SL/TP lines were added
        shapes = fig.layout.shapes
        assert len(shapes) >= 4  # 2 trades * (1 SL line + 1 TP line)

    def test_trade_overlay_disabled_removes_markers(self, sample_bars: pd.DataFrame, sample_trades: pd.DataFrame):
        """When show_trades is False, trade traces and SL/TP shapes are omitted."""
        fig = create_candlestick_chart(
            sample_bars,
            trades=sample_trades,
            show_trades=False,
        )
        trace_names = [t.name for t in fig.data if t.name]
        assert "Trade Entry (Long)" not in trace_names
        assert "Trade Entry (Short)" not in trace_names

    def test_smc_dealing_range_lines(self, sample_bars: pd.DataFrame):
        """When smc_result has equilibrium, dealing range boundary lines are drawn."""
        smc_res = analyze_smc(sample_bars, symbol="XAUUSD", timeframe="M15")
        fig = create_candlestick_chart(
            sample_bars,
            smc_result=smc_res,
            show_dealing_range=True,
        )
        assert fig is not None
        if smc_res.equilibrium is not None:
            # Check shapes count includes equilibrium line
            assert len(fig.layout.shapes) > 0

    def test_equity_curve_chart_valid_and_empty(self):
        """create_equity_curve_chart handles valid series and empty dataframe."""
        dates = pd.date_range("2026-01-01", periods=10, freq="1D", tz="UTC")
        eq_df = pd.DataFrame({
            "time": dates,
            "realized_equity": [10000, 10100, 10050, 10200, 10150, 10300, 10250, 10400, 10350, 10500],
            "equity": [10000, 10120, 10040, 10220, 10140, 10310, 10230, 10420, 10340, 10510],
        })
        fig = create_equity_curve_chart(eq_df, initial_capital=10000.0)
        assert fig is not None
        trace_names = [t.name for t in fig.data if t.name]
        assert "Realized Equity" in trace_names
        assert "Mark-to-Market Equity" in trace_names
        assert "Drawdown %" in trace_names

        # Empty test
        fig_empty = create_equity_curve_chart(pd.DataFrame())
        assert fig_empty is not None
        assert any("No equity curve" in a.text for a in fig_empty.layout.annotations)

    def test_pnl_distribution_chart(self, sample_trades: pd.DataFrame):
        """create_pnl_distribution_chart generates histogram with mean line."""
        fig = create_pnl_distribution_chart(sample_trades)
        assert fig is not None
        assert len(fig.data) == 1
        assert fig.data[0].type == "histogram"

        fig_empty = create_pnl_distribution_chart(pd.DataFrame())
        assert any("No closed trades" in a.text for a in fig_empty.layout.annotations)

    def test_trade_outcome_donut(self, sample_trades: pd.DataFrame):
        """create_trade_outcome_donut renders pie chart with exit reason breakdown."""
        fig = create_trade_outcome_donut(sample_trades)
        assert fig is not None
        assert fig.data[0].type == "pie"
        assert fig.data[0].hole == 0.55

    def test_performance_by_session_chart(self, sample_trades: pd.DataFrame):
        """create_performance_by_session_chart generates bar chart across sessions."""
        fig = create_performance_by_session_chart(sample_trades)
        assert fig is not None
        assert fig.data[0].type == "bar"
        assert len(fig.data[0].x) == 5  # 5 standard session windows

    def test_preset_full_research_y_autoscale_toggle(self, sample_bars: pd.DataFrame):
        """Verify Full SMC Research y-axis toggle behaviour between visible clamping and full range."""
        smc_res = analyze_smc(sample_bars, symbol="XAUUSD", timeframe="M15")

        # 1. With autoscale_y_to_visible=True (default focus)
        fig_clamped = create_candlestick_chart(
            sample_bars,
            smc_result=smc_res,
            preset="full_research",
            autoscale_y_to_visible=True,
            visible_bars=50,
        )
        assert fig_clamped.layout.yaxis.range is not None
        clamped_min, clamped_max = fig_clamped.layout.yaxis.range
        vis_low = sample_bars.iloc[-50:]["low"].min()
        vis_high = sample_bars.iloc[-50:]["high"].max()
        assert clamped_min < vis_low
        assert clamped_max > vis_high

        # 2. With autoscale_y_to_visible=False (expand to distant historical zones)
        fig_expanded = create_candlestick_chart(
            sample_bars,
            smc_result=smc_res,
            preset="full_research",
            autoscale_y_to_visible=False,
            visible_bars=50,
        )
        assert fig_expanded.layout.yaxis.range is None
        assert fig_expanded.layout.yaxis.autorange is True

    def test_all_four_presets_generate_valid_figures(self, sample_bars: pd.DataFrame):
        """Verify all four chart presets produce valid figures with compliant trace hierarchies."""
        smc_res = analyze_smc(sample_bars, symbol="XAUUSD", timeframe="M15")
        presets = ["clean", "smc_analysis", "full_research", "custom"]

        for preset in presets:
            fig = create_candlestick_chart(
                sample_bars,
                smc_result=smc_res,
                preset=preset,
                visible_bars=50,
            )
            assert fig is not None
            assert len(fig.data) >= 1  # Candlestick trace present
            assert fig.data[0].type == "candlestick"


