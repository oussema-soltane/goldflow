import json
import pandas as pd
import numpy as np
import pytest
from pathlib import Path

from src.data.cleaner import clean_market_data, save_processed_data, compute_file_sha256
from src.data.loader import save_raw_data
from tests.test_validator import create_sample_ohlc_df


class TestMarketDataCleaner:
    def test_clean_deduplication(self):
        """Duplicates must be removed while keeping the first occurrence."""
        df = create_sample_ohlc_df(10)
        # Duplicate row 3
        df_with_dup = pd.concat([df, df.iloc[[3]]], ignore_index=True)
        assert len(df_with_dup) == 11

        cleaned, audit = clean_market_data(df_with_dup, symbol="XAUUSD", timeframe="M15")
        assert len(cleaned) == 10
        assert audit["duplicates_removed"] == 1
        assert cleaned["time"].is_monotonic_increasing

    def test_clean_removes_invalid_ohlc(self):
        """Rows violating OHLC boundaries must be discarded."""
        df = create_sample_ohlc_df(10)
        # Corrupt row 2 (high < open) and row 5 (low > close)
        df.loc[2, "high"] = df.loc[2, "open"] - 5.0
        df.loc[5, "low"] = df.loc[5, "close"] + 5.0

        cleaned, audit = clean_market_data(df, symbol="XAUUSD", timeframe="M15")
        assert len(cleaned) == 8
        assert audit["invalid_ohlc_removed"] == 2

    def test_clean_sorts_chronologically(self):
        """Unsorted data must be sorted ascending by timestamp."""
        df = create_sample_ohlc_df(10)
        # Shuffle order
        df_shuffled = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
        assert not df_shuffled["time"].is_monotonic_increasing

        cleaned, _ = clean_market_data(df_shuffled, symbol="XAUUSD", timeframe="M15")
        assert cleaned["time"].is_monotonic_increasing

    def test_zero_price_interpolation(self):
        """
        Critical Principle:
        The cleaner must NEVER interpolate or invent synthetic prices between missing bars.
        Rows are filtered or kept; no intermediate rows are fabricated.
        """
        df = create_sample_ohlc_df(5)
        # Introduce a 2-hour gap between row 1 and row 2
        df.loc[2:, "time"] = df.loc[2:, "time"] + pd.Timedelta(hours=2)

        cleaned, _ = clean_market_data(df, symbol="XAUUSD", timeframe="M15")
        # Length must still be exactly 5 (no fabricated bars added)
        assert len(cleaned) == 5

    def test_no_double_truncation_of_candles(self):
        """
        Regression Test:
        Valid completed candles must NOT be truncated twice.
        clean_market_data does not discard trailing bars if OHLC is valid.
        """
        df = create_sample_ohlc_df(15)
        cleaned, audit = clean_market_data(df, symbol="XAUUSD", timeframe="M15")
        # Exactly 15 valid bars in, exactly 15 valid bars out
        assert len(cleaned) == 15
        assert audit["original_rows"] == 15
        assert audit["final_rows"] == 15

    def test_raw_data_remains_unchanged(self, tmp_path):
        """
        Data Provenance:
        Raw CSV files must remain completely unmodified by cleaning and processing.
        """
        raw_df = create_sample_ohlc_df(10)
        raw_path = save_raw_data(raw_df, "XAUUSD", "M15", output_dir=tmp_path / "raw")
        raw_content_before = raw_path.read_bytes()

        # Run cleaning and saving of processed data
        cleaned_df, audit = clean_market_data(raw_df, symbol="XAUUSD", timeframe="M15")
        save_processed_data(
            cleaned_df, "XAUUSD", "M15", output_dir=tmp_path / "processed",
            raw_source_path=raw_path, audit_log=audit
        )

        # Raw file on disk must be byte-for-byte identical
        raw_content_after = raw_path.read_bytes()
        assert raw_content_before == raw_content_after

    def test_provenance_sidecar_generation(self, tmp_path):
        """
        Provenance Sidecar:
        save_processed_data must create both clean CSV and a JSON metadata sidecar
        with valid SHA-256 hash and audit details.
        """
        df = create_sample_ohlc_df(8)
        raw_path = save_raw_data(df, "XAUUSD", "H1", output_dir=tmp_path / "raw")
        expected_hash = compute_file_sha256(raw_path)

        cleaned, audit = clean_market_data(df, "XAUUSD", "H1")
        csv_file, meta_file = save_processed_data(
            cleaned, "XAUUSD", "H1",
            output_dir=tmp_path / "processed",
            raw_source_path=raw_path,
            audit_log=audit
        )

        assert csv_file.exists()
        assert meta_file.exists()

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        assert meta["symbol"] == "XAUUSD"
        assert meta["timeframe"] == "H1"
        assert meta["raw_file_sha256"] == expected_hash
        assert meta["raw_row_count"] == 8
        assert meta["processed_row_count"] == 8
        assert "UTC" in meta["timezone_convention"]


class TestProvenanceSourceMetadata:
    def test_source_metadata_is_persisted_to_sidecar(self, tmp_path):
        import json
        import pandas as pd
        from src.data.cleaner import save_processed_data

        df = pd.DataFrame({
            "time": pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC"),
            "open": [2650.0, 2651.0, 2652.0],
            "high": [2651.0, 2652.0, 2653.0],
            "low": [2649.0, 2650.0, 2651.0],
            "close": [2650.5, 2651.5, 2652.5],
        })
        _, meta_path = save_processed_data(
            df, "XAUUSD", "H1", output_dir=tmp_path,
            source_metadata={
                "source": "MetaTrader 5 API",
                "is_synthetic": False,
                "retrieval_date_utc": "2026-01-01T03:00:00+00:00",
                "incomplete_bar_excluded": True,
            },
        )
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["source"] == "MetaTrader 5 API"
        assert meta["is_synthetic"] is False
        assert meta["incomplete_bar_excluded"] is True

