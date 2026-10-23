"""
Unit tests for Unified ICT Analysis Engine (Orchestrator).

Verifies end-to-end integration across Swings, BOS/CHoCH, FVGs, Sweeps, and Order Blocks.
"""

import pandas as pd
import pytest

from src.data.loader import generate_synthetic_gold_data
from src.ict.engine import ICTAnalysisResult, analyze_market_structure
from src.ict.models import MarketTrend


class TestICTEngineOrchestrator:
    def test_empty_dataframe_handling(self):
        """Empty input must return an empty ICTAnalysisResult cleanly."""
        res = analyze_market_structure(pd.DataFrame())
        assert isinstance(res, ICTAnalysisResult)
        assert res.total_bars == 0
        assert res.current_trend == MarketTrend.NEUTRAL
        assert len(res.swings) == 0
        assert len(res.structure_breaks) == 0

    def test_end_to_end_synthetic_gold_analysis(self):
        """Run complete ICT engine on 200 bars of synthetic gold data."""
        df, _ = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="M15", n_bars=200, seed=42)
        res = analyze_market_structure(
            df=df,
            symbol="XAUUSD",
            timeframe="M15",
            swing_window=2,
            break_on_close=True,
            min_gap_points=0.2,
            track_mitigation=True,
        )

        assert isinstance(res, ICTAnalysisResult)
        assert res.total_bars == 200
        assert res.current_trend in (MarketTrend.BULLISH, MarketTrend.BEARISH, MarketTrend.NEUTRAL)
        assert len(res.swings) > 0
        assert res.bos_count >= 0
        assert res.choch_count >= 0
        assert len(res.fvgs) >= 0

        # Summary dictionary
        summary = res.summary()
        assert summary["symbol"] == "XAUUSD"
        assert summary["timeframe"] == "M15"
        assert summary["total_bars"] == 200
        assert "current_trend" in summary
        assert "total_swings" in summary
        assert "active_fvgs" in summary

    def test_chart_with_ict_overlays(self):
        """Verify that create_candlestick_chart accepts and visualizes an ICTAnalysisResult."""
        from src.visualization.charts import create_candlestick_chart
        df, _ = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="M15", n_bars=80, seed=42)
        res = analyze_market_structure(df, symbol="XAUUSD", timeframe="M15")
        fig = create_candlestick_chart(df, symbol="XAUUSD", timeframe="M15", ict_result=res)
        assert fig is not None
        assert len(fig.data) >= 2  # Candles + volume (+ overlay traces)



def test_displacement_is_exposed_by_integrated_engine_and_summary():
    """The integrated Phase 2 result exposes displacement indices and count."""
    df, _ = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="M15", n_bars=120, seed=37)
    result = analyze_market_structure(df, displacement_atr_period=5, displacement_multiplier=0.8)
    assert isinstance(result.displacement_indices, list)
    assert all(0 <= i < len(df) for i in result.displacement_indices)
    assert result.summary()["displacement_candles"] == len(result.displacement_indices)
