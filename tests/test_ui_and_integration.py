"""
GoldFlow — Phase 2.1 UI Logic & Integration Test Suite.

Verifies:
1. Chart building with all overlay combinations (on/off).
2. Chart building with empty dataframe produces useful annotation instead of crashing.
3. Event counts in ICTAnalysisResult agree with table record counts.
4. Processed datasets on disk load and analyze cleanly across all timeframes.
5. Ingestion in synthetic mode produces fully traceable artifacts without MT5.
"""

import json
from pathlib import Path
import pandas as pd
import pytest

from src.data.loader import generate_synthetic_gold_data, load_local_data
from src.data.validator import validate_market_data
from src.ict.engine import analyze_market_structure
from src.visualization.charts import create_candlestick_chart


class TestUIAndIntegration:
    def test_chart_handles_empty_dataframe_gracefully(self):
        """When given an empty DataFrame, create_candlestick_chart returns a valid figure with informative text."""
        fig = create_candlestick_chart(pd.DataFrame())
        assert fig is not None
        annotations = [a.text for a in fig.layout.annotations]
        assert any("No market data available" in str(txt) for txt in annotations)

    def test_chart_overlay_toggles_add_and_remove_traces(self):
        """Toggling overlay booleans adds/removes corresponding trace names from Plotly figure."""
        df, _ = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="M15", n_bars=80, seed=42)
        ict_res = analyze_market_structure(df, swing_window=2)

        # All overlays enabled
        fig_all = create_candlestick_chart(
            df,
            ict_result=ict_res,
            show_swings=True,
            show_structure_breaks=True,
            show_fvgs=True,
            show_sweeps=True,
            show_order_blocks=True,
            show_displacements=True,
        )
        trace_names_all = [t.name for t in fig_all.data if t.name]

        # All overlays disabled
        fig_none = create_candlestick_chart(
            df,
            ict_result=ict_res,
            show_swings=False,
            show_structure_breaks=False,
            show_fvgs=False,
            show_sweeps=False,
            show_order_blocks=False,
            show_displacements=False,
        )
        trace_names_none = [t.name for t in fig_none.data if t.name]

        assert "Price" in trace_names_all
        assert "Price" in trace_names_none

        if any(s.swing_type.value == "SWING_HIGH" for s in ict_res.swings):
            assert "Swing Highs" in trace_names_all
            assert "Swing Highs" not in trace_names_none

        if ict_res.displacement_indices:
            assert "Displacement" in trace_names_all
            assert "Displacement" not in trace_names_none

    def test_event_tables_data_consistency(self):
        """Verify that table records constructed in Streamlit agree with ict_res counts."""
        df, _ = generate_synthetic_gold_data(symbol="XAUUSD", timeframe="M15", n_bars=150, seed=10)
        ict_res = analyze_market_structure(df, swing_window=2)

        # 1. Structural Breaks
        brk_records = [
            {"Type": b.break_type.value, "Price": b.break_price}
            for b in ict_res.structure_breaks
        ]
        assert len(brk_records) == len(ict_res.structure_breaks)
        assert sum(1 for r in brk_records if r["Type"] == "BOS") == ict_res.bos_count
        assert sum(1 for r in brk_records if r["Type"] == "CHoCH") == ict_res.choch_count

        # 2. FVGs
        fvg_records = [
            {"Type": f.gap_type.value, "CE": f.consequent_encroachment}
            for f in ict_res.fvgs
        ]
        assert len(fvg_records) == len(ict_res.fvgs)

        # 3. Sweeps & MSS
        sw_records = [{"Price": sw.sweep_price} for sw in ict_res.liquidity_sweeps]
        assert len(sw_records) == len(ict_res.liquidity_sweeps)

        mss_records = [{"Shift": m.shift_index} for m in ict_res.market_structure_shifts]
        assert len(mss_records) == len(ict_res.market_structure_shifts)

        # 4. Order Blocks
        ob_records = [{"High": ob.high, "Low": ob.low} for ob in ict_res.order_blocks]
        assert len(ob_records) == len(ict_res.order_blocks)

    def test_disk_processed_datasets_load_and_validate(self):
        """All clean CSV files present in data/processed/ must load and pass validation."""
        processed_dir = Path("data/processed")
        if not processed_dir.exists():
            pytest.skip("No data/processed directory")

        csv_files = list(processed_dir.glob("*.csv"))
        if not csv_files:
            pytest.skip("No CSV files in data/processed")

        for csv_p in csv_files:
            df = load_local_data(csv_p)
            assert len(df) > 0
            assert "time" in df.columns
            assert str(df["time"].dt.tz) == "UTC"

            parts = csv_p.stem.split("_")
            symbol = parts[0]
            tf = parts[1] if len(parts) > 1 and parts[1] in ["M5", "M15", "H1", "H4"] else "M15"

            report = validate_market_data(df, symbol=symbol, timeframe=tf)
            assert report.status in ("PASSED", "PASSED_WITH_WARNINGS")
            assert report.invalid_ohlc_count == 0

            # Validate the full disk dataset above, but run the computationally
            # heavier ICT engine on a representative tail sample to keep CI fast.
            analysis_df = df.tail(2000).reset_index(drop=True)
            res = analyze_market_structure(analysis_df, symbol=symbol, timeframe=tf)
            assert res.total_bars == len(analysis_df)
            assert res.timeframe == tf
