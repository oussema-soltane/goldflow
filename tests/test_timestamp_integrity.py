"""Regression tests for timestamp conversion and legacy-data quarantine.

These tests never assume that a fixed UTC offset is valid for all historical bars.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data.loader import convert_mt5_epoch_times
from src.data.cleaner import clean_market_data, save_processed_data
from src.research.data_readiness import audit_dataset, evaluate_research_readiness

ROOT = Path(__file__).resolve().parent.parent
TIMEFRAMES = ("M5", "M15", "H1", "H4")


def _encode_wall_clock_as_epoch(value: str) -> int:
    """Simulate a server-local wall clock incorrectly encoded as UTC epoch seconds."""
    return int(pd.Timestamp(value).tz_localize("UTC").timestamp())


def test_posix_utc_mode_does_not_shift_epoch():
    raw = 1791985183
    times, correction = convert_mt5_epoch_times([raw], timestamp_mode="posix_utc")
    assert times.iloc[0] == pd.Timestamp("2026-10-14T13:39:43Z")
    assert correction.tolist() == [0]


def test_server_wall_clock_mode_uses_winter_dst_offset():
    raw = _encode_wall_clock_as_epoch("2026-01-15 12:00:00")
    times, correction = convert_mt5_epoch_times(
        [raw], timestamp_mode="server_wall_clock", server_timezone="Europe/Athens"
    )
    assert times.iloc[0] == pd.Timestamp("2026-01-15T10:00:00Z")
    assert correction.tolist() == [-7200]


def test_server_wall_clock_mode_uses_summer_dst_offset():
    raw = _encode_wall_clock_as_epoch("2026-07-15 12:00:00")
    times, correction = convert_mt5_epoch_times(
        [raw], timestamp_mode="server_wall_clock", server_timezone="Europe/Athens"
    )
    assert times.iloc[0] == pd.Timestamp("2026-07-15T09:00:00Z")
    assert correction.tolist() == [-10800]


def test_server_wall_clock_requires_timezone():
    raw = _encode_wall_clock_as_epoch("2026-01-15 12:00:00")
    with pytest.raises(ValueError, match="server_timezone is required"):
        convert_mt5_epoch_times([raw], timestamp_mode="server_wall_clock")


def test_invalid_timestamp_mode_is_rejected():
    with pytest.raises(ValueError, match="Unsupported timestamp_mode"):
        convert_mt5_epoch_times([0], timestamp_mode="guess")


@pytest.mark.parametrize(
    "wall_clock",
    [
        "2026-10-25 03:30:00",  # ambiguous in Europe/Athens at autumn transition
        "2026-03-29 03:30:00",  # nonexistent in Europe/Athens at spring transition
    ],
)
def test_dst_ambiguous_or_nonexistent_wall_clock_is_not_guessed(wall_clock):
    raw = _encode_wall_clock_as_epoch(wall_clock)
    with pytest.raises(ValueError, match="Could not safely localize"):
        convert_mt5_epoch_times(
            [raw], timestamp_mode="server_wall_clock", server_timezone="Europe/Athens"
        )



def test_loader_uses_explicit_timestamp_mode_and_preserves_raw_epoch(monkeypatch):
    import src.data.loader as loader

    raw_times = [
        _encode_wall_clock_as_epoch("2026-01-15 12:00:00"),
        _encode_wall_clock_as_epoch("2026-01-15 12:05:00"),
    ]
    dtype = [
        ("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
        ("close", "f8"), ("tick_volume", "i8"), ("spread", "i8"), ("real_volume", "i8"),
    ]
    rates = np.array([
        (raw_times[0], 100.0, 101.0, 99.0, 100.5, 10, 2, 0),
        (raw_times[1], 100.5, 101.5, 100.0, 101.0, 12, 2, 0),
    ], dtype=dtype)

    class FakeMT5:
        TIMEFRAME_M5 = 5
        def symbol_select(self, symbol, enable):
            return True
        def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
            assert start_pos == 1
            return rates
        def last_error(self):
            return (0, "ok")

    monkeypatch.setattr(loader, "mt5", FakeMT5())
    df, meta = loader.fetch_historical_bars(
        "XAUUSD", "M5", n_bars=2, exclude_incomplete=True,
        timestamp_mode="server_wall_clock", server_timezone="Europe/Athens",
    )
    assert df["time"].tolist() == [
        pd.Timestamp("2026-01-15T10:00:00Z"),
        pd.Timestamp("2026-01-15T10:05:00Z"),
    ]
    assert df["time_raw_epoch"].tolist() == raw_times
    assert df["timestamp_correction_applied_seconds"].tolist() == [-7200, -7200]
    assert meta["timestamp_mode"] == "server_wall_clock"
    assert meta["timestamp_correction_applied_seconds"] == -7200
    assert meta["raw_timestamp_epoch_preserved"] is True


def test_loader_default_posix_mode_does_not_apply_timezone_shift(monkeypatch):
    import src.data.loader as loader

    raw_time = int(pd.Timestamp("2026-10-14T13:39:43Z").timestamp())
    dtype = [
        ("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
        ("close", "f8"), ("tick_volume", "i8"), ("spread", "i8"), ("real_volume", "i8"),
    ]
    rates = np.array([(raw_time, 100.0, 101.0, 99.0, 100.5, 10, 2, 0)], dtype=dtype)

    class FakeMT5:
        TIMEFRAME_M5 = 5
        def symbol_select(self, symbol, enable):
            return True
        def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
            return rates
        def last_error(self):
            return (0, "ok")

    monkeypatch.setattr(loader, "mt5", FakeMT5())
    df, meta = loader.fetch_historical_bars("XAUUSD", "M5", n_bars=1)
    assert df["time"].iloc[0] == pd.Timestamp("2026-10-14T13:39:43Z")
    assert df["timestamp_correction_applied_seconds"].tolist() == [0]
    assert meta["timestamp_mode"] == "posix_utc"

def test_cleaner_drops_raw_timestamp_audit_columns():
    df = pd.DataFrame({
        "time": pd.to_datetime(["2026-01-01T00:00:00Z"]),
        "time_raw_epoch": [1767225600],
        "timestamp_correction_applied_seconds": [0],
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
        "tick_volume": [10], "spread": [2], "real_volume": [0],
    })
    cleaned, _ = clean_market_data(df)
    assert "time_raw_epoch" not in cleaned.columns
    assert "timestamp_correction_applied_seconds" not in cleaned.columns
    assert cleaned["time"].iloc[0] == pd.Timestamp("2026-01-01T00:00:00Z")


def test_sidecar_propagates_timestamp_and_provenance_fields(tmp_path):
    df = pd.DataFrame({
        "time": pd.to_datetime(["2026-01-01T00:00:00Z"]),
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.5],
        "tick_volume": [10], "spread": [2], "real_volume": [0],
    })
    source = {
        "source": "MetaTrader 5 API",
        "source_verification_status": "declared_not_independently_verified",
        "raw_timestamp_epoch_preserved": True,
        "retrieval_date_utc": "2026-01-01T00:05:00+00:00",
        "incomplete_bar_excluded": True,
        "timestamp_mode": "server_wall_clock",
        "timestamp_representation": "server-local wall-clock encoded as epoch-like seconds",
        "server_timezone": "Europe/Athens",
        "server_utc_offset_hours": 2,
        "timestamp_correction_applied_seconds": -7200,
        "timestamp_correction_applied_seconds_min": -7200,
        "timestamp_correction_applied_seconds_max": -7200,
        "timestamp_mode_verified": True,
        "timestamp_integrity_status": "verified",
        "is_synthetic": False,
    }
    raw_path = tmp_path / "XAUUSD_M5_raw.csv"
    raw_path.write_text("test raw file", encoding="utf-8")
    _, meta_path = save_processed_data(
        df, "XAUUSD", "M5", output_dir=tmp_path,
        raw_source_path=raw_path, audit_log={"original_rows": 1}, source_metadata=source,
    )
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["timestamp_mode"] == "server_wall_clock"
    assert meta["server_timezone"] == "Europe/Athens"
    assert meta["timestamp_correction_applied_seconds"] == -7200
    assert meta["raw_timestamp_epoch_preserved"] is True
    assert meta["source_verification_status"] == "declared_not_independently_verified"


def test_readiness_blocks_legacy_fixed_offset_metadata():
    df = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=100, freq="h", tz="UTC"),
        "open": np.full(100, 100.0), "high": np.full(100, 101.0),
        "low": np.full(100, 99.0), "close": np.full(100, 100.5),
    })
    meta = {
        "source": "MetaTrader 5 API",
        "is_synthetic": False,
        "retrieval_date_utc": "2026-01-05T04:00:00+00:00",
        "timestamp_mode": "legacy_fixed_offset_unverified",
        "timestamp_integrity_status": "blocked_legacy_fixed_offset",
    }
    report = audit_dataset(df, meta, "H1")
    result = evaluate_research_readiness(
        {"H1": report}, minimum_bars={"H1": 1}
    )
    assert result["overall_status"] == "BLOCKED"
    assert any("Timestamp conversion" in b for b in result["blockers"])


def test_readiness_accepts_verified_timestamp_metadata():
    """Verified data with verified timestamp mode passes timestamp gates."""
    df = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=100, freq="h", tz="UTC"),
        "open": np.full(100, 100.0), "high": np.full(100, 101.0),
        "low": np.full(100, 99.0), "close": np.full(100, 100.5),
    })
    meta = {
        "source": "MetaTrader 5 API",
        "is_synthetic": False,
        "retrieval_date_utc": "2026-01-05T04:00:00+00:00",
        "timestamp_mode": "server_wall_clock",
        "server_timezone": "Europe/Athens",
        "timestamp_mode_verified": True,
        "timestamp_integrity_status": "verified",
        "raw_timestamp_epoch_preserved": True,
    }
    report = audit_dataset(df, meta, "H1")
    result = evaluate_research_readiness(
        {"H1": report}, minimum_bars={"H1": 1}
    )
    assert not any("Timestamp conversion" in b for b in result.get("blockers", []))


def test_readiness_blocks_normalized_unverified_metadata():
    """Normalized but unverified data must remain blocked for time-based research."""
    df = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=100, freq="h", tz="UTC"),
        "open": np.full(100, 100.0), "high": np.full(100, 101.0),
        "low": np.full(100, 99.0), "close": np.full(100, 100.5),
    })
    meta = {
        "source": "MetaTrader 5 API",
        "is_synthetic": False,
        "retrieval_date_utc": "2026-01-05T04:00:00+00:00",
        "timestamp_mode": "posix_utc",
        "timestamp_mode_verified": False,
        "timestamp_integrity_status": "normalized_by_explicit_mode",
        "raw_timestamp_epoch_preserved": True,
    }
    report = audit_dataset(df, meta, "H1")
    result = evaluate_research_readiness(
        {"H1": report}, minimum_bars={"H1": 1}
    )
    assert result["overall_status"] == "BLOCKED"
    assert any("Timestamp conversion is not verified" in b for b in result["blockers"])


def test_legacy_project_sidecars_are_explicitly_quarantined():
    """Sidecars must distinguish verified data from unverified/legacy states, both of which must stay quarantined."""
    for tf in TIMEFRAMES:
        path = ROOT / "data" / "processed" / f"XAUUSD_{tf}_clean.meta.json"
        if not path.exists():
            pytest.skip(f"Current project data for {tf} is not present.")
        meta = json.loads(path.read_text(encoding="utf-8"))
        status = meta.get("timestamp_integrity_status")
        if status == "verified":
            assert meta.get("raw_timestamp_epoch_preserved") is True
            assert meta.get("timestamp_mode") in {"server_wall_clock", "posix_utc"}
            assert meta.get("timestamp_mode_verified") is True
        elif status == "normalized_by_explicit_mode":
            # Normalized with unverified mode: distinct state that must remain blocked
            assert meta.get("timestamp_mode_verified") is False
        else:
            # Unrecoverable legacy data with fixed offset
            assert status == "blocked_legacy_fixed_offset"
            assert meta.get("timestamp_mode") == "legacy_fixed_offset_unverified"
            assert meta.get("raw_timestamp_epoch_preserved") is False


def test_current_files_remain_marked_as_declared_not_independently_verified():
    for tf in TIMEFRAMES:
        path = ROOT / "data" / "processed" / f"XAUUSD_{tf}_clean.meta.json"
        if not path.exists():
            pytest.skip(f"Current project data for {tf} is not present.")
        meta = json.loads(path.read_text(encoding="utf-8"))
        assert meta.get("source_verification_status") == "declared_not_independently_verified"
