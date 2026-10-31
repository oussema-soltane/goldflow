"""Tests for canonical data isolation and protection against data loss.

Ensures that:
1. Synthetic data ingestion NEVER modifies files in canonical data/raw or data/processed.
2. Candidates with fewer bars or truncated date coverage are rejected unless allow_shrink=True.
3. Unverified timestamp mode is rejected from promotion to canonical paths.
4. save_processed_data guards against synthetic routing into canonical paths.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from src.data.cleaner import clean_market_data, save_processed_data
from src.data.loader import save_raw_data
from scripts.download_data import (
    run_pipeline,
    validate_download_candidate,
)

ROOT = Path(__file__).resolve().parent.parent


def _hash_canonical_files() -> dict[str, str]:
    """Compute sha256 for all canonical files."""
    canonical_paths = [
        ROOT / "data" / "raw" / "XAUUSD_H1_raw.csv",
        ROOT / "data" / "raw" / "XAUUSD_H4_raw.csv",
        ROOT / "data" / "raw" / "XAUUSD_M15_raw.csv",
        ROOT / "data" / "raw" / "XAUUSD_M5_raw.csv",
        ROOT / "data" / "processed" / "XAUUSD_H1_clean.csv",
        ROOT / "data" / "processed" / "XAUUSD_H4_clean.csv",
        ROOT / "data" / "processed" / "XAUUSD_M15_clean.csv",
        ROOT / "data" / "processed" / "XAUUSD_M5_clean.csv",
        ROOT / "data" / "processed" / "XAUUSD_H1_clean.meta.json",
        ROOT / "data" / "processed" / "XAUUSD_H4_clean.meta.json",
        ROOT / "data" / "processed" / "XAUUSD_M15_clean.meta.json",
        ROOT / "data" / "processed" / "XAUUSD_M5_clean.meta.json",
        ROOT / "configs" / "smc_v1_frozen.json",
    ]
    return {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in canonical_paths
        if p.is_file()
    }


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
        })
    return pd.DataFrame(rows)


def _make_sample_meta(n: int = 100) -> dict:
    return {
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "raw_row_count": n,
        "processed_row_count": n,
        "retrieval_date_utc": "2026-02-05T12:00:00Z",
        "raw_timestamp_epoch_preserved": True,
        "incomplete_bar_excluded": True,
        "timestamp_mode": "posix_utc",
        "timestamp_mode_verified": True,
        "timestamp_integrity_status": "verified",
    }


class TestCanonicalIsolation:
    """Ensure canonical data files are strictly protected from synthetic operations."""

    def test_synthetic_pipeline_leaves_canonical_data_untouched(self, tmp_path):
        pre_hashes = _hash_canonical_files()
        assert len(pre_hashes) >= 12, "Pre-condition: canonical files must exist"

        # Run synthetic pipeline for M15
        summary_path = tmp_path / "synthetic_summary.json"
        exit_code = run_pipeline(
            symbol="XAUUSD",
            timeframes=["M15"],
            bars=50,
            use_synthetic=True,
            acquisition_summary_path=summary_path,
        )
        assert exit_code == 0

        # Check post-hashes match pre-hashes exactly
        post_hashes = _hash_canonical_files()
        assert pre_hashes == post_hashes, "Canonical files were modified by synthetic pipeline run!"

    def test_save_processed_data_guard_rejects_synthetic_to_canonical_dir(self):
        df = _make_sample_df(10)
        with pytest.raises(ValueError, match="Synthetic data must NOT be written to canonical"):
            save_processed_data(
                df,
                symbol="XAUUSD",
                timeframe="M15",
                output_dir=Path("data/processed"),
                synthetic=True,
            )


class TestCoverageAndShrinkGuards:
    """Ensure small or truncated candidates cannot replace active canonical datasets."""

    def test_candidate_smaller_than_existing_rejected(self, tmp_path):
        existing_sidecar = tmp_path / "XAUUSD_M15_clean.meta.json"
        existing_sidecar.write_text(json.dumps({
            "processed_row_count": 5000,
            "start_time": "2025-01-01T00:00:00+00:00",
            "end_time": "2026-10-20T00:00:00+00:00",
        }), encoding="utf-8")

        df = _make_sample_df(100)
        meta = _make_sample_meta(100)

        with pytest.raises(ValueError, match="would SHRINK the existing dataset"):
            validate_download_candidate(
                df_raw=df,
                df_clean=df,
                meta=meta,
                timeframe="M15",
                requested_bars=100,
                symbol="XAUUSD",
                existing_sidecar_path=existing_sidecar,
                allow_shrink=False,
            )

    def test_candidate_smaller_allowed_with_explicit_override(self, tmp_path):
        existing_sidecar = tmp_path / "XAUUSD_M15_clean.meta.json"
        existing_sidecar.write_text(json.dumps({
            "processed_row_count": 5000,
            "start_time": "2026-02-01T00:00:00+00:00",
            "end_time": "2026-02-05T00:00:00+00:00",
        }), encoding="utf-8")

        df = _make_sample_df(100, start="2026-02-01 00:00:00")
        meta = _make_sample_meta(100)

        # allow_shrink=True must not raise
        validate_download_candidate(
            df_raw=df,
            df_clean=df,
            meta=meta,
            timeframe="M15",
            requested_bars=100,
            symbol="XAUUSD",
            existing_sidecar_path=existing_sidecar,
            allow_shrink=True,
        )

    def test_candidate_truncated_history_rejected(self, tmp_path):
        existing_sidecar = tmp_path / "XAUUSD_M15_clean.meta.json"
        existing_sidecar.write_text(json.dumps({
            "processed_row_count": 100,
            "start_time": "2026-01-01T00:00:00+00:00",
            "end_time": "2026-02-01T00:00:00+00:00",
        }), encoding="utf-8")

        # Candidate has 100 rows, but starts on 2026-02-02 (losing January)
        df = _make_sample_df(100, start="2026-02-02 08:00:00")
        meta = _make_sample_meta(100)

        with pytest.raises(ValueError, match="AFTER the existing dataset start"):
            validate_download_candidate(
                df_raw=df,
                df_clean=df,
                meta=meta,
                timeframe="M15",
                requested_bars=100,
                symbol="XAUUSD",
                existing_sidecar_path=existing_sidecar,
                allow_shrink=False,
            )

    def test_unverified_wall_clock_timestamp_mode_rejected(self):
        df = _make_sample_df(100)
        meta = _make_sample_meta(100)
        meta["timestamp_mode"] = "server_wall_clock"
        meta["timestamp_mode_verified"] = False

        with pytest.raises(ValueError, match="timestamp_mode_verified is False"):
            validate_download_candidate(
                df_raw=df,
                df_clean=df,
                meta=meta,
                timeframe="M15",
                requested_bars=100,
                symbol="XAUUSD",
            )
