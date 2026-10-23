"""
Unit & Integration tests for Data Loader & MT5 Connector (Phase 1).
"""

import pytest
import pandas as pd
from pathlib import Path

from src.data.loader import (
    TIMEFRAME_MAP,
    generate_synthetic_gold_data,
    load_local_data,
    save_raw_data,
    check_mt5_status,
)


class TestDataLoader:
    def test_timeframe_mapping_keys(self):
        """Supported timeframes must include H4, H1, M15, M5."""
        for tf in ["H4", "H1", "M15", "M5"]:
            assert tf in TIMEFRAME_MAP

    def test_synthetic_data_structure(self):
        """Synthetic benchmark generator should create valid OHLC data with metadata."""
        df, meta = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="M15", n_bars=50)

        assert len(df) == 50
        assert meta["symbol"] == "XAUUSD"
        assert meta["timeframe"] == "M15"
        assert meta["is_synthetic"] is True

        required_cols = ["time", "open", "high", "low", "close", "tick_volume", "spread"]
        for col in required_cols:
            assert col in df.columns

        # Verify geometric integrity of synthetic output
        assert (df["high"] >= df["open"]).all()
        assert (df["high"] >= df["close"]).all()
        assert (df["low"] <= df["open"]).all()
        assert (df["low"] <= df["close"]).all()

    def test_save_and_load_local_data(self, tmp_path):
        """Ensure raw CSV can be saved and reloaded faithfully."""
        df, _ = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="H1", n_bars=20)
        saved_path = save_raw_data(df, "XAUUSD", "H1", output_dir=tmp_path)

        assert saved_path.exists()

        reloaded = load_local_data(saved_path)
        assert len(reloaded) == 20
        assert pd.api.types.is_datetime64_any_dtype(reloaded["time"])

    def test_mt5_status_diagnostics(self):
        """Diagnostic function must return structured dictionary without throwing exceptions."""
        status = check_mt5_status()
        assert "package_installed" in status
        assert "terminal_installed" in status
        assert "connected" in status
        assert "actionable_message" in status
        # Verify no credentials or sensitive tokens exposed
        assert "password" not in status

    def test_symbol_filename_sanitization(self, tmp_path):
        """
        Regression Test:
        Symbols containing characters illegal in Windows file paths (/, \\, :, *, ?, ", <, >, |)
        must be safely sanitized so files can actually be created on disk without error.
        """
        from src.data.loader import sanitize_symbol_for_filename

        assert sanitize_symbol_for_filename("XAU/USD") == "XAU_USD"
        assert sanitize_symbol_for_filename("GOLD/EUR") == "GOLD_EUR"
        assert sanitize_symbol_for_filename("XAU:USD") == "XAU_USD"
        assert sanitize_symbol_for_filename("XAU\\USD") == "XAU_USD"
        assert sanitize_symbol_for_filename("XAUUSD.a") == "XAUUSD.a"

        # Verify disk writing with slashed symbol
        df, _ = generate_synthetic_gold_data(symbol="XAU/USD", timeframe="M15", n_bars=10)
        saved_file = save_raw_data(df, "XAU/USD", "M15", output_dir=tmp_path)

        assert saved_file.exists()
        assert "XAU_USD_M15_raw.csv" in saved_file.name

        # Reloading should succeed
        reloaded = load_local_data(saved_file)
        assert len(reloaded) == 10

    def test_chart_rangeslider_configuration(self):
        """
        Visualization Test:
        Verify that create_candlestick_chart configures rangeslider_visible=False
        across all subplots so no overlapping slider obscures the volume bars.
        """
        from src.visualization.charts import create_candlestick_chart

        df, _ = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="M15", n_bars=30)
        fig = create_candlestick_chart(df, symbol="XAUUSD", timeframe="M15", show_volume=True)

        # Check layout xaxes
        assert fig.layout.xaxis.rangeslider.visible is False
        if hasattr(fig.layout, "xaxis2"):
            assert fig.layout.xaxis2.rangeslider.visible is False

    def test_mocked_completed_candle_indexing(self):
        """
        Mock Test:
        Verify MT5 copy_rates_from_pos argument behavior:
        1. When exclude_incomplete=True, start_pos must be 1.
        2. When exclude_incomplete=False, start_pos must be 0.
        3. Timestamps are converted to explicit UTC-aware datetime64.
        4. Downstream cleaner does NOT remove a second completed bar.
        """
        from unittest.mock import patch
        import numpy as np
        from src.data.loader import fetch_historical_bars
        from src.data.cleaner import clean_market_data

        # Structured numpy recarray mimicking MT5 rates output
        mock_rates = np.array([
            (1773000000, 2650.0, 2655.0, 2648.0, 2652.0, 500, 15, 0),
            (1773000900, 2652.0, 2656.0, 2651.0, 2654.0, 600, 16, 0),
            (1773001800, 2654.0, 2658.0, 2653.0, 2657.0, 700, 14, 0),
        ], dtype=[
            ('time', '<i8'), ('open', '<f8'), ('high', '<f8'), ('low', '<f8'),
            ('close', '<f8'), ('tick_volume', '<u8'), ('spread', '<i4'), ('real_volume', '<u8')
        ])

        with patch("src.data.loader.mt5") as mock_mt5:
            mock_mt5.TIMEFRAME_M15 = 15
            mock_mt5.symbol_select.return_value = True
            mock_mt5.copy_rates_from_pos.return_value = mock_rates

            # 1. exclude_incomplete=True -> must pass start_pos=1
            df_ex, meta_ex = fetch_historical_bars("XAUUSD", "M15", n_bars=3, exclude_incomplete=True)
            mock_mt5.copy_rates_from_pos.assert_called_with("XAUUSD", 15, 1, 3)
            assert len(df_ex) == 3
            assert str(df_ex["time"].dt.tz) == "UTC"
            assert meta_ex["incomplete_bar_excluded"] is True
            assert "UTC" in meta_ex["timezone_convention"]

            # 2. exclude_incomplete=False -> must pass start_pos=0
            df_inc, meta_inc = fetch_historical_bars("XAUUSD", "M15", n_bars=3, exclude_incomplete=False)
            mock_mt5.copy_rates_from_pos.assert_called_with("XAUUSD", 15, 0, 3)
            assert len(df_inc) == 3
            assert meta_inc["incomplete_bar_excluded"] is False

            # 3. Downstream cleaner preserves all 3 bars (no double-removal)
            df_clean, audit = clean_market_data(df_ex, symbol="XAUUSD", timeframe="M15")
            assert len(df_clean) == 3
            assert audit["final_rows"] == 3
            assert audit["duplicates_removed"] == 0
            assert audit["invalid_ohlc_removed"] == 0

    def test_synthetic_data_zero_or_negative_bars(self):
        """Zero or negative n_bars must return an empty DataFrame with valid schema."""
        for n in [0, -1, -100]:
            df, meta = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="M15", n_bars=n)
            assert len(df) == 0
            assert meta["row_count"] == 0
            assert meta["start_time"] is None
            assert meta["end_time"] is None
            assert "time" in df.columns
            assert "open" in df.columns
            assert "close" in df.columns
            assert pd.api.types.is_datetime64_any_dtype(df["time"])
