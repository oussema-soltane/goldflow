"""
Unit and regression tests for downloader safety, exit codes, and transactional replacement.

Tests:
1. Partial responses (fewer bars than requested) are rejected and cannot overwrite existing datasets.
2. A failed second timeframe after a successful first timeframe produces a nonzero exit code and explicit per-timeframe results.
3. Invalid timestamps (non-monotonic, duplicate, non-UTC) are rejected.
4. Future data relative to retrieval time is rejected.
5. Failed file write triggers fail-closed atomic rollback to preserve existing data.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from scripts.download_data import (
    run_pipeline,
    transactionally_stage_and_promote,
    validate_download_candidate,
)


def _make_sample_df(n: int = 100, start: str = "2026-02-02 08:00:00", freq: str = "15min") -> pd.DataFrame:
    times = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
    rows = []
    base = 2650.0
    for i, t in enumerate(times):
        p = base + i * 0.1
        rows.append({
            "time": t,
            "open": p,
            "high": p + 0.5,
            "low": p - 0.5,
            "close": p + 0.1,
            "tick_volume": 100,
            "spread": 20,
            "real_volume": 0,
            "time_raw_epoch": int(t.timestamp()),
            "timestamp_correction_applied_seconds": -10800,
        })
    return pd.DataFrame(rows)


def _make_sample_meta(n: int = 100) -> dict:
    return {
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "requested_bars": n,
        "actual_rows_received": n,
        "retrieval_date_utc": "2026-02-05T00:00:00Z",
        "source": "MetaTrader 5 API",
        "is_synthetic": False,
        "raw_timestamp_epoch_preserved": True,
        "incomplete_bar_excluded": True,
        "timestamp_mode": "server_wall_clock",
        "server_timezone": "Europe/Athens",
        "timestamp_mode_verified": True,
        "timestamp_integrity_status": "verified",
    }


class TestDownloaderValidationGate:
    def test_partial_response_rejected(self):
        df_raw = _make_sample_df(1500)
        df_clean = df_raw.copy()
        meta = _make_sample_meta(1500)

        with pytest.raises(ValueError, match="Insufficient raw history"):
            validate_download_candidate(
                df_raw=df_raw,
                df_clean=df_clean,
                meta=meta,
                timeframe="M15",
                requested_bars=5000,
                symbol="XAUUSD",
            )

    def test_future_candles_rejected(self):
        df_raw = _make_sample_df(100, start="2026-02-05 12:00:00")
        df_clean = df_raw.copy()
        meta = _make_sample_meta(100)
        meta["retrieval_date_utc"] = "2026-02-05T10:00:00Z"  # 2 hours before bars

        with pytest.raises(ValueError, match="future candle"):
            validate_download_candidate(
                df_raw=df_raw,
                df_clean=df_clean,
                meta=meta,
                timeframe="M15",
                requested_bars=100,
                symbol="XAUUSD",
            )

    def test_non_monotonic_timestamps_rejected(self):
        df_raw = _make_sample_df(100)
        df_clean = df_raw.copy()
        # Invert last two rows
        t_temp = df_clean.loc[98, "time"]
        df_clean.loc[98, "time"] = df_clean.loc[99, "time"]
        df_clean.loc[99, "time"] = t_temp
        meta = _make_sample_meta(100)

        with pytest.raises(ValueError, match="monotonically increasing"):
            validate_download_candidate(
                df_raw=df_raw,
                df_clean=df_clean,
                meta=meta,
                timeframe="M15",
                requested_bars=100,
                symbol="XAUUSD",
            )

    def test_duplicate_timestamps_rejected(self):
        df_raw = _make_sample_df(100)
        df_clean = df_raw.copy()
        df_clean.loc[5, "time"] = df_clean.loc[4, "time"]
        meta = _make_sample_meta(100)

        with pytest.raises(ValueError, match="duplicate timestamp"):
            validate_download_candidate(
                df_raw=df_raw,
                df_clean=df_clean,
                meta=meta,
                timeframe="M15",
                requested_bars=100,
                symbol="XAUUSD",
            )

    def test_ohlc_boundary_violation_rejected(self):
        df_raw = _make_sample_df(100)
        df_clean = df_raw.copy()
        df_clean.loc[10, "high"] = df_clean.loc[10, "low"] - 1.0  # high < low
        meta = _make_sample_meta(100)

        with pytest.raises(ValueError, match="OHLC boundary violations"):
            validate_download_candidate(
                df_raw=df_raw,
                df_clean=df_clean,
                meta=meta,
                timeframe="M15",
                requested_bars=100,
                symbol="XAUUSD",
            )


class TestTransactionalReplacement:
    def test_successful_transactional_promotion(self, tmp_path):
        raw_dir = tmp_path / "raw"
        processed_dir = tmp_path / "processed"
        df_raw = _make_sample_df(100)
        df_clean = df_raw.copy()
        meta = _make_sample_meta(100)
        audit = {"operations": ["Test clean"]}

        raw_path, clean_path, meta_path = transactionally_stage_and_promote(
            df_raw=df_raw,
            df_clean=df_clean,
            meta=meta,
            audit_log=audit,
            symbol="XAUUSD",
            timeframe="M15",
            raw_dir=raw_dir,
            processed_dir=processed_dir,
        )

        assert raw_path.is_file()
        assert clean_path.is_file()
        assert meta_path.is_file()
        assert raw_path.stat().st_size > 0
        assert clean_path.stat().st_size > 0
        assert meta_path.stat().st_size > 0

    def test_atomic_rollback_on_failed_promotion(self, tmp_path):
        raw_dir = tmp_path / "raw"
        processed_dir = tmp_path / "processed"
        raw_dir.mkdir(parents=True)
        processed_dir.mkdir(parents=True)

        # Existing files
        existing_raw = raw_dir / "XAUUSD_M15_raw.csv"
        existing_clean = processed_dir / "XAUUSD_M15_clean.csv"
        existing_meta = processed_dir / "XAUUSD_M15_clean.meta.json"
        existing_raw.write_text("existing,raw,data")
        existing_clean.write_text("existing,clean,data")
        existing_meta.write_text(json.dumps({"version": "existing"}))

        df_raw = _make_sample_df(100)
        df_clean = df_raw.copy()
        meta = _make_sample_meta(100)

        # Simulate failure during promotion of meta file
        with patch("os.replace", side_effect=[None, None, OSError("Disk write failed!")]):
            with pytest.raises(RuntimeError, match="safely restored"):
                transactionally_stage_and_promote(
                    df_raw=df_raw,
                    df_clean=df_clean,
                    meta=meta,
                    audit_log={},
                    symbol="XAUUSD",
                    timeframe="M15",
                    raw_dir=raw_dir,
                    processed_dir=processed_dir,
                )

        # Verify original files remain intact
        assert existing_raw.read_text() == "existing,raw,data"
        assert existing_clean.read_text() == "existing,clean,data"
        assert json.loads(existing_meta.read_text()) == {"version": "existing"}


class TestDownloaderPipelineExitCodes:
    def test_pipeline_fails_when_one_timeframe_fails(self, tmp_path):
        """If H1 succeeds but M15 fails, exit code must be 2 (nonzero).

        The acquisition summary is written to an isolated tmp_path location
        so that the real reports/data_acquisition_summary.json is never touched.
        """
        df_good = _make_sample_df(100)
        meta_good = _make_sample_meta(100)
        isolated_summary = tmp_path / "data_acquisition_summary.json"

        def mock_fetch(sym, tf, **kwargs):
            if tf == "H1":
                return df_good, dict(meta_good, timeframe="H1")
            else:
                raise RuntimeError(f"Simulated MT5 feed failure for {tf}")

        with patch("scripts.download_data.check_mt5_status", return_value={"connected": True, "package_installed": True, "terminal_installed": True, "terminal_path": "x", "actionable_message": "OK"}), \
             patch("scripts.download_data.discover_gold_symbols", return_value=[{"name": "XAUUSD", "description": "Gold", "digits": 2, "spread": 20, "visible": True}]), \
             patch("scripts.download_data.fetch_historical_bars", side_effect=mock_fetch), \
             patch("scripts.download_data.transactionally_stage_and_promote", return_value=(Path("raw.csv"), Path("clean.csv"), Path("meta.json"))), \
             patch("scripts.download_data.shutdown_mt5"):

            code = run_pipeline(
                symbol="XAUUSD",
                timeframes=["H1", "M15"],
                bars=100,
                use_synthetic=False,
                timestamp_mode="server_wall_clock",
                server_timezone="Europe/Athens",
                timestamp_mode_verified=False,
                acquisition_summary_path=isolated_summary,
            )

            assert code == 2

            # Check that the ISOLATED summary (not the real report) recorded the failure
            assert isolated_summary.is_file(), "Isolated summary was not created"
            with open(isolated_summary) as f:
                summary = json.load(f)
            assert summary["overall_status"] == "FAILED"
            assert summary["timeframe_results"]["H1"]["status"] == "SUCCESS"
            assert summary["timeframe_results"]["M15"]["status"] == "FAILED"

    def test_simulated_failure_does_not_contaminate_real_reports(self, tmp_path):
        """Regression test: running a simulated pipeline failure must not overwrite
        the real reports/data_acquisition_summary.json.
        """
        real_report = Path("reports/data_acquisition_summary.json")

        # Record original content (if the file exists)
        original_content: str | None = None
        if real_report.is_file():
            original_content = real_report.read_text(encoding="utf-8")

        isolated_summary = tmp_path / "isolated_summary.json"
        df_good = _make_sample_df(100)
        meta_good = _make_sample_meta(100)

        def mock_fetch(sym, tf, **kwargs):
            raise RuntimeError("Simulated failure")

        with patch("scripts.download_data.check_mt5_status", return_value={"connected": True, "package_installed": True, "terminal_installed": True, "terminal_path": "x", "actionable_message": "OK"}), \
             patch("scripts.download_data.discover_gold_symbols", return_value=[{"name": "XAUUSD", "description": "Gold", "digits": 2, "spread": 20, "visible": True}]), \
             patch("scripts.download_data.fetch_historical_bars", side_effect=mock_fetch), \
             patch("scripts.download_data.shutdown_mt5"):

            run_pipeline(
                symbol="XAUUSD",
                timeframes=["M15"],
                bars=100,
                use_synthetic=False,
                timestamp_mode="posix_utc",
                timestamp_mode_verified=False,
                acquisition_summary_path=isolated_summary,
            )

        # The real report must be identical to what it was before (or absent if it never existed)
        if original_content is not None:
            assert real_report.is_file(), "Real report disappeared after simulated failure test"
            assert real_report.read_text(encoding="utf-8") == original_content, (
                "Real reports/data_acquisition_summary.json was modified by the simulated failure test"
            )
        else:
            # If the real report didn't exist before, it must still not exist
            assert not real_report.is_file(), (
                "Simulated failure test created reports/data_acquisition_summary.json when it did not exist"
            )
