"""
GoldFlow Phase 3B.1 -- MT5 Data Pipeline Regression and Integration Tests.

Coverage:
  1.  MT5 init failure
  2.  Missing/unavailable symbol
  3.  Empty and incomplete historical responses
  4.  No synthetic fallback during real download
  5.  Accurate metadata and source provenance
  6.  Epoch-seconds to UTC conversion
  7.  Detection of arbitrary/incorrect timezone shifts
  8.  Duplicate and out-of-order timestamps
  9.  Invalid OHLC values
  10. Incomplete (forming) candle exclusion
  11. Atomic write safety
  12. Distinct timeframe dataset checks
  13. Weekend/session-gap handling
  14. SMC and ICT engine compatibility
  15. Provenance: MT5 vs synthetic distinction

All MT5-dependent tests use monkeypatching [mock-mt5]. No live terminal required.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

import src.data.loader as loader
from src.data.cleaner import clean_market_data, save_processed_data
from src.data.loader import (
    convert_mt5_epoch_times,
    fetch_historical_bars,
    generate_synthetic_gold_data,
    save_raw_data,
)
from src.data.validator import validate_market_data
from src.ict.engine import analyze_market_structure
from src.research.data_readiness import (
    audit_dataset,
    classify_gaps,
    evaluate_research_readiness,
    ohlc_hash,
)
from src.smc.engine import SMCConfig, analyze_smc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rates(start_epoch=1_769_000_000, n=5, interval_sec=300, base=2650.0):
    """Structured recarray mimicking MT5 copy_rates_from_pos output."""
    dtype = [
        ("time", "<i8"), ("open", "<f8"), ("high", "<f8"),
        ("low", "<f8"), ("close", "<f8"),
        ("tick_volume", "<u8"), ("spread", "<i4"), ("real_volume", "<u8"),
    ]
    rows = [
        (
            start_epoch + i * interval_sec,
            base + i * 0.5,
            base + i * 0.5 + 1.2,
            base + i * 0.5 - 0.8,
            base + i * 0.5 + 0.3,
            500 + i, 15, 0,
        )
        for i in range(n)
    ]
    return np.array(rows, dtype=dtype)


def _make_fake_mt5(rates=None, symbol_select_ok=True, tick_time=None):
    fake = MagicMock()
    fake.TIMEFRAME_M5 = 5
    fake.TIMEFRAME_M15 = 15
    fake.TIMEFRAME_H1 = 16385
    fake.TIMEFRAME_H4 = 16388
    # Test fixture provides an MT5 enum constant so the capture path must resolve
    # trade_calc_mode=0 through the package constant rather than a hard-coded map.
    fake.SYMBOL_CALC_MODE_FOREX = 0
    fake.symbol_select.return_value = symbol_select_ok
    fake.copy_rates_from_pos.return_value = rates
    fake.last_error.return_value = (0, "ok")
    if tick_time is not None:
        tick = MagicMock()
        tick.time = tick_time
        fake.symbol_info_tick.return_value = tick
    else:
        fake.symbol_info_tick.return_value = None
    return fake


def _good_meta():
    return {
        "source": "MetaTrader 5 API",
        "is_synthetic": False,
        "retrieval_date_utc": "2026-10-19T21:00:00+00:00",
        "timestamp_mode": "posix_utc",
        "timestamp_integrity_status": "verified",
        "raw_timestamp_epoch_preserved": True,
        "timestamp_mode_verified": True,
    }


def _clean_df(n=200, tf="M5"):
    df, _ = generate_synthetic_gold_data("XAUUSD", tf, n_bars=n, seed=7)
    df = df.drop(columns=["time_raw_epoch", "timestamp_correction_applied_seconds"], errors="ignore")
    df_clean, _ = clean_market_data(df)
    return df_clean


# ---------------------------------------------------------------------------
# 1. MT5 initialization failure
# ---------------------------------------------------------------------------

def test_raises_when_mt5_module_is_none(monkeypatch):
    """[mock-mt5] No MT5 library -> RuntimeError, no silent synthetic fallback."""
    monkeypatch.setattr(loader, "mt5", None)
    with pytest.raises(RuntimeError, match="MetaTrader5 library is not available"):
        fetch_historical_bars("XAUUSD", "M5", n_bars=10)


def test_no_synthetic_returned_on_mt5_unavailable(monkeypatch):
    """[mock-mt5] Unavailable MT5 causes fetch to raise; synthetic generator still works standalone."""
    monkeypatch.setattr(loader, "mt5", None)
    with pytest.raises(RuntimeError):
        fetch_historical_bars("XAUUSD", "H1", n_bars=100)
    df, meta = generate_synthetic_gold_data("XAUUSD", "H1", n_bars=5)
    assert meta["is_synthetic"] is True


# ---------------------------------------------------------------------------
# 2. Symbol selection failure
# ---------------------------------------------------------------------------

def test_raises_on_symbol_select_failure(monkeypatch):
    """[mock-mt5] Unavailable symbol raises ValueError."""
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(symbol_select_ok=False))
    with pytest.raises(ValueError, match="could not be selected"):
        fetch_historical_bars("BADGOLD", "M5", n_bars=10)


def test_error_message_includes_symbol_name(monkeypatch):
    """[mock-mt5] ValueError must mention the attempted symbol."""
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(symbol_select_ok=False))
    with pytest.raises(ValueError) as exc:
        fetch_historical_bars("XAUUSD.ZZZ", "M15", n_bars=10)
    assert "XAUUSD.ZZZ" in str(exc.value)


# ---------------------------------------------------------------------------
# 3. Empty and incomplete historical responses
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [None, np.array([])])
def test_raises_on_empty_mt5_response(monkeypatch, bad):
    """[mock-mt5] None or empty rates raise RuntimeError."""
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(rates=bad))
    with pytest.raises(RuntimeError, match="0 bars"):
        fetch_historical_bars("XAUUSD", "M5", n_bars=10)


# ---------------------------------------------------------------------------
# 4. No synthetic fallback during real download
# ---------------------------------------------------------------------------

def test_symbol_failure_does_not_fall_back_to_synthetic(monkeypatch):
    """[mock-mt5] Symbol failure raises; no synthetic data returned."""
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(symbol_select_ok=False))
    with pytest.raises(ValueError):
        fetch_historical_bars("XAUUSD", "M5", n_bars=10)


def test_empty_response_does_not_fall_back_to_synthetic(monkeypatch):
    """[mock-mt5] Empty response raises; no synthetic data returned."""
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(rates=None))
    with pytest.raises(RuntimeError):
        fetch_historical_bars("XAUUSD", "H1", n_bars=100)


def test_real_fetch_does_not_emit_synthetic_metadata(monkeypatch):
    """[mock-mt5] Real fetch must not set is_synthetic=True in metadata."""
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(rates=_make_rates()))
    df, meta = fetch_historical_bars("XAUUSD", "M5", n_bars=5)
    assert meta.get("is_synthetic") is not True
    assert "synthetic" not in str(meta.get("source", "")).lower()


# ---------------------------------------------------------------------------
# 5. Metadata and source provenance
# ---------------------------------------------------------------------------

def test_real_fetch_metadata_fields(monkeypatch):
    """[mock-mt5] All required provenance fields are emitted correctly."""
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(rates=_make_rates(n=10)))
    df, meta = fetch_historical_bars("XAUUSD", "M5", n_bars=10)
    assert meta["source"] == "MetaTrader 5 API"
    assert meta["is_synthetic"] is False
    assert meta["symbol"] == "XAUUSD"
    assert meta["timeframe"] == "M5"
    assert meta["row_count"] == len(df)
    assert meta["requested_bars"] == 10
    assert meta["actual_rows_received"] == 10
    assert meta["raw_timestamp_epoch_preserved"] is True
    assert meta["incomplete_bar_excluded"] is True
    assert meta["timestamp_mode"] in {"posix_utc", "server_wall_clock"}
    assert "retrieval_date_utc" in meta
    assert "start_time" in meta and meta["start_time"] is not None
    assert "end_time" in meta and meta["end_time"] is not None


def test_mt5_symbol_execution_specification_is_captured_and_persisted(monkeypatch, tmp_path):
    """Actual broker instrument properties survive into the processed sidecar."""
    fake = _make_fake_mt5(rates=_make_rates(n=10))
    fake.symbol_info.return_value = SimpleNamespace(
        digits=2, point=0.01, trade_contract_size=100.0,
        volume_min=0.01, volume_step=0.01, volume_max=100.0,
        trade_tick_size=0.01, trade_tick_value=1.0,
        trade_tick_value_profit=1.0, trade_tick_value_loss=1.0,
        currency_base="XAU", currency_profit="USD", currency_margin="USD",
        trade_calc_mode=0, trade_stops_level=0, trade_freeze_level=0,
        spread=20, spread_float=True,
    )
    monkeypatch.setattr(loader, "mt5", fake)
    df, source_meta = fetch_historical_bars("XAUUSD", "M5", n_bars=10)
    spec = source_meta["execution_specification"]
    assert source_meta["execution_specification_status"] == "captured_complete"
    assert spec["point"] == pytest.approx(0.01)
    assert spec["trade_contract_size"] == pytest.approx(100.0)
    assert spec["volume_step"] == pytest.approx(0.01)
    df_clean, audit = clean_market_data(df)
    _, meta_path = save_processed_data(
        df_clean, "XAUUSD", "M5", output_dir=tmp_path,
        audit_log=audit, source_metadata=source_meta,
    )
    sidecar = json.loads(meta_path.read_text())
    assert sidecar["execution_specification_status"] == "captured_complete"
    assert sidecar["execution_specification"]["trade_tick_value"] == pytest.approx(1.0)
    assert sidecar["execution_specification"]["currency_profit"] == "USD"


@pytest.mark.parametrize("constants", [
    {},
    {"SYMBOL_CALC_MODE_FOREX": 0, "SYMBOL_CALC_MODE_CFD": 0},
], ids=["empty-map", "ambiguous-duplicate-code"])
def test_calc_mode_capture_is_incomplete_without_unique_symbolic_package_mapping(monkeypatch, constants):
    """A numeric mode is incomplete when no unique active-package constant resolves it."""
    fake = _make_fake_mt5(rates=_make_rates(n=5))
    fake.symbol_info.return_value = SimpleNamespace(
        digits=2, point=0.01, trade_contract_size=100.0,
        volume_min=0.01, volume_step=0.01, volume_max=100.0,
        trade_tick_size=0.01, trade_tick_value=1.0,
        currency_base="XAU", currency_profit="USD", currency_margin="USD",
        trade_calc_mode=0,
    )
    monkeypatch.setattr(loader, "mt5", fake)
    monkeypatch.setattr(loader, "_mt5_calc_mode_constant_values", lambda: constants)

    _, meta = fetch_historical_bars("XAUUSD", "M5", n_bars=5)

    assert meta["execution_specification_status"] == "captured_incomplete"
    assert meta["execution_specification"]["trade_calc_mode"] == 0
    assert meta["execution_specification"]["trade_calc_mode_name"] is None
    assert meta["execution_specification"]["trade_calc_mode_name_source"] is None
    assert meta["execution_specification"]["trade_calc_mode_constant_values"] == constants


def test_missing_mt5_symbol_specs_are_not_invented(monkeypatch):
    """An unavailable symbol_info record must stay unavailable, not use defaults."""
    fake = _make_fake_mt5(rates=_make_rates(n=5))
    fake.symbol_info.return_value = None
    monkeypatch.setattr(loader, "mt5", fake)
    _, meta = fetch_historical_bars("XAUUSD", "M5", n_bars=5)
    assert meta["execution_specification_status"] == "unavailable"
    assert meta["execution_specification"]["point"] is None
    assert meta["execution_specification"]["trade_contract_size"] is None


def test_actual_rows_reported_not_requested(monkeypatch):
    """[mock-mt5] Row count reflects actual returned rows, not requested bars."""
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(rates=_make_rates(n=7)))
    df, meta = fetch_historical_bars("XAUUSD", "M5", n_bars=100)
    assert meta["row_count"] == 7
    assert meta["requested_bars"] == 100
    assert meta["actual_rows_received"] == 7
    assert len(df) == 7


def test_metadata_contains_no_credentials(monkeypatch):
    """[mock-mt5] Metadata must not expose passwords, tokens or secrets."""
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(rates=_make_rates(n=5)))
    _, meta = fetch_historical_bars("XAUUSD", "M5", n_bars=5)
    meta_str = json.dumps(meta).lower()
    for forbidden in ("password", "token", "secret", "auth", "credential"):
        assert forbidden not in meta_str


def test_sidecar_source_is_metatrader5_api(monkeypatch, tmp_path):
    """[mock-mt5] Sidecar from real fetch records MetaTrader 5 API."""
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(rates=_make_rates(n=5)))
    df, src_meta = fetch_historical_bars("XAUUSD", "M5", n_bars=5)
    df_clean, audit = clean_market_data(df)
    _, meta_path = save_processed_data(
        df_clean, "XAUUSD", "M5", output_dir=tmp_path,
        audit_log=audit, source_metadata=src_meta,
    )
    sidecar = json.loads(meta_path.read_text())
    assert sidecar["source"] == "MetaTrader 5 API"
    assert sidecar["is_synthetic"] is not True


# ---------------------------------------------------------------------------
# 6. Epoch-seconds to UTC conversion
# ---------------------------------------------------------------------------

def test_known_epoch_converts_to_correct_utc():
    epoch = 1_700_000_000  # 2023-11-14 22:13:20 UTC
    times, corrections = convert_mt5_epoch_times([epoch], timestamp_mode="posix_utc")
    assert times.iloc[0] == pd.Timestamp("2023-11-14T22:13:20Z")
    assert corrections.tolist() == [0]


def test_zero_epoch_is_unix_origin():
    times, _ = convert_mt5_epoch_times([0], timestamp_mode="posix_utc")
    assert times.iloc[0] == pd.Timestamp("1970-01-01T00:00:00Z")


def test_all_timestamps_utc_aware(monkeypatch):
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(rates=_make_rates(n=20)))
    df, _ = fetch_historical_bars("XAUUSD", "M5", n_bars=20)
    assert str(df["time"].dt.tz) == "UTC"


def test_raw_epoch_preserved_in_df(monkeypatch):
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(rates=_make_rates(n=3, start_epoch=1_769_000_000)))
    df, meta = fetch_historical_bars("XAUUSD", "M5", n_bars=3)
    assert "time_raw_epoch" in df.columns
    assert df["time_raw_epoch"].iloc[0] == 1_769_000_000
    assert meta["raw_timestamp_epoch_preserved"] is True


# ---------------------------------------------------------------------------
# 7. Detection of arbitrary/incorrect timezone shifts
# ---------------------------------------------------------------------------

def test_posix_mode_applies_no_offset():
    epoch = 1_769_500_000
    times, corrections = convert_mt5_epoch_times([epoch], timestamp_mode="posix_utc")
    expected = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
    assert times.iloc[0].to_pydatetime() == expected
    assert corrections.tolist() == [0]


def test_server_wall_clock_without_timezone_rejected():
    with pytest.raises(ValueError, match="server_timezone is required"):
        convert_mt5_epoch_times([1_769_500_000], timestamp_mode="server_wall_clock")


def test_unsupported_mode_rejected():
    with pytest.raises(ValueError, match="Unsupported timestamp_mode"):
        convert_mt5_epoch_times([1_769_500_000], timestamp_mode="fixed_minus_3h")


def test_legacy_fixed_offset_blocks_readiness():
    df = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=50, freq="h", tz="UTC"),
        "open": np.full(50, 2650.0), "high": np.full(50, 2651.0),
        "low": np.full(50, 2649.0), "close": np.full(50, 2650.5),
    })
    meta = {
        "source": "MetaTrader 5 API", "is_synthetic": None,
        "retrieval_date_utc": "2026-01-03T04:00:00+00:00",
        "timestamp_mode": "legacy_fixed_offset_unverified",
        "timestamp_integrity_status": "blocked_legacy_fixed_offset",
        "raw_timestamp_epoch_preserved": False, "timestamp_mode_verified": False,
    }
    report = audit_dataset(df, meta, "H1")
    result = evaluate_research_readiness({"H1": report}, minimum_bars={"H1": 1})
    assert result["overall_status"] == "BLOCKED"
    blockers = " ".join(result["blockers"])
    assert "timestamp" in blockers.lower() or "Timestamp" in blockers


def test_three_hour_fixed_shift_blocks_readiness():
    """A -3h fixed shift in sidecar metadata must block research readiness."""
    df = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=100, freq="h", tz="UTC"),
        "open": np.full(100, 2650.0), "high": np.full(100, 2651.0),
        "low": np.full(100, 2649.0), "close": np.full(100, 2650.5),
    })
    meta = {
        "source": "MetaTrader 5 API", "is_synthetic": None,
        "retrieval_date_utc": "2026-01-05T05:00:00+00:00",
        "timestamp_mode": "legacy_fixed_offset_unverified",
        "timestamp_integrity_status": "blocked_legacy_fixed_offset",
        "timestamp_correction_applied_seconds": -10800,
        "raw_timestamp_epoch_preserved": False, "timestamp_mode_verified": False,
    }
    report = audit_dataset(df, meta, "H1")
    result = evaluate_research_readiness({"H1": report}, minimum_bars={"H1": 1})
    assert result["overall_status"] == "BLOCKED"


# ---------------------------------------------------------------------------
# 8. Duplicate and out-of-order timestamps
# ---------------------------------------------------------------------------

def test_duplicate_timestamps_detected():
    times = pd.date_range("2026-01-01", periods=50, freq="5min", tz="UTC").tolist()
    times[25] = times[24]
    df = pd.DataFrame({
        "time": times, "open": np.full(50, 2650.0),
        "high": np.full(50, 2651.0), "low": np.full(50, 2649.0), "close": np.full(50, 2650.5),
    })
    report = audit_dataset(df, _good_meta(), "M5")
    assert report["duplicate_timestamps"] > 0


def test_out_of_order_timestamps_detected():
    times = pd.date_range("2026-01-01", periods=50, freq="5min", tz="UTC").tolist()
    times[10], times[11] = times[11], times[10]
    df = pd.DataFrame({
        "time": times, "open": np.full(50, 2650.0),
        "high": np.full(50, 2651.0), "low": np.full(50, 2649.0), "close": np.full(50, 2650.5),
    })
    report = audit_dataset(df, _good_meta(), "M5")
    assert not report["monotonic"]


def test_duplicate_timestamps_block_readiness():
    times = pd.date_range("2026-01-01", periods=50, freq="5min", tz="UTC").tolist()
    times[30] = times[29]
    df = pd.DataFrame({
        "time": times, "open": np.full(50, 2650.0),
        "high": np.full(50, 2651.0), "low": np.full(50, 2649.0), "close": np.full(50, 2650.5),
    })
    report = audit_dataset(df, _good_meta(), "M5")
    result = evaluate_research_readiness({"M5": report}, minimum_bars={"M5": 1})
    assert result["overall_status"] == "BLOCKED"


# ---------------------------------------------------------------------------
# 9. Invalid OHLC values
# ---------------------------------------------------------------------------

def test_high_below_close_is_flagged():
    df = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=3, freq="5min", tz="UTC"),
        "open":  [2650.0, 2651.0, 2649.0],
        "high":  [2651.0, 2649.0, 2652.0],  # row 1: high < close
        "low":   [2648.0, 2648.0, 2648.0],
        "close": [2650.5, 2652.0, 2650.0],
    })
    report = audit_dataset(df, _good_meta(), "M5")
    assert report["ohlc_violations"] > 0


def test_zero_prices_are_flagged():
    df = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=3, freq="5min", tz="UTC"),
        "open":  [2650.0, 0.0, 2649.0],  # row 1: zero open
        "high":  [2651.0, 2651.0, 2652.0],
        "low":   [2648.0, 2648.0, 2648.0],
        "close": [2650.5, 2650.5, 2650.0],
    })
    report = audit_dataset(df, _good_meta(), "M5")
    assert report["zero_neg_prices"] > 0


def test_ohlc_violations_block_readiness():
    df = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=3, freq="5min", tz="UTC"),
        "open":  [2650.0, 2651.0, 2649.0],
        "high":  [2651.0, 2649.0, 2652.0],  # violation
        "low":   [2648.0, 2648.0, 2648.0],
        "close": [2650.5, 2652.0, 2650.0],
    })
    report = audit_dataset(df, _good_meta(), "M5")
    result = evaluate_research_readiness({"M5": report}, minimum_bars={"M5": 1})
    assert result["overall_status"] == "BLOCKED"


# ---------------------------------------------------------------------------
# 10. Incomplete (forming) candle exclusion
# ---------------------------------------------------------------------------

def test_exclude_incomplete_uses_start_pos_1(monkeypatch):
    """[mock-mt5] exclude_incomplete=True must use start_pos=1."""
    fake = _make_fake_mt5(rates=_make_rates(n=5))
    monkeypatch.setattr(loader, "mt5", fake)
    fetch_historical_bars("XAUUSD", "M5", n_bars=5, exclude_incomplete=True)
    fake.copy_rates_from_pos.assert_called_with("XAUUSD", 5, 1, 5)


def test_include_incomplete_uses_start_pos_0(monkeypatch):
    """[mock-mt5] exclude_incomplete=False must use start_pos=0."""
    fake = _make_fake_mt5(rates=_make_rates(n=5))
    monkeypatch.setattr(loader, "mt5", fake)
    fetch_historical_bars("XAUUSD", "M5", n_bars=5, exclude_incomplete=False)
    fake.copy_rates_from_pos.assert_called_with("XAUUSD", 5, 0, 5)


def test_incomplete_bar_excluded_in_metadata(monkeypatch):
    """[mock-mt5] Metadata records that incomplete bar was excluded."""
    fake = _make_fake_mt5(rates=_make_rates(n=5))
    monkeypatch.setattr(loader, "mt5", fake)
    _, meta = fetch_historical_bars("XAUUSD", "M5", n_bars=5, exclude_incomplete=True)
    assert meta["incomplete_bar_excluded"] is True


# ---------------------------------------------------------------------------
# 11. Atomic write safety
# ---------------------------------------------------------------------------

def test_existing_file_preserved_when_save_raises(tmp_path):
    """Failed write must not destroy the existing valid dataset."""
    original = "time,open,high,low,close\n2026-01-01T00:00:00+00:00,2650,2651,2649,2650.5\n"
    target = tmp_path / "XAUUSD_M5_raw.csv"
    target.write_text(original, encoding="utf-8")

    with patch.object(pd.DataFrame, "to_csv", side_effect=IOError("disk full")):
        with pytest.raises(IOError):
            df = pd.DataFrame({
                "time": pd.to_datetime(["2026-01-02T00:00:00Z"]),
                "open": [2660.0], "high": [2661.0], "low": [2659.0], "close": [2660.5],
                "tick_volume": [100], "spread": [15], "real_volume": [0],
                "time_raw_epoch": [1767225600],
                "timestamp_correction_applied_seconds": [0],
            })
            save_raw_data(df, "XAUUSD", "M5", output_dir=tmp_path)

    assert target.read_text(encoding="utf-8") == original


def test_no_orphan_temp_files_on_failure(tmp_path):
    """After a failed write, no .tmp. files should remain."""
    with patch.object(pd.DataFrame, "to_csv", side_effect=IOError("fail")):
        with pytest.raises(IOError):
            df = pd.DataFrame({
                "time": pd.to_datetime(["2026-01-01T00:00:00Z"]),
                "open": [2650.0], "high": [2651.0], "low": [2649.0], "close": [2650.5],
                "tick_volume": [100], "spread": [15], "real_volume": [0],
                "time_raw_epoch": [1767225600],
                "timestamp_correction_applied_seconds": [0],
            })
            save_raw_data(df, "XAUUSD", "M5", output_dir=tmp_path)
    assert len(list(tmp_path.glob("*.tmp.*"))) == 0


def test_successful_write_produces_correct_file(tmp_path):
    """Successful write produces the target file with correct rows, no temp files."""
    df = pd.DataFrame({
        "time": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:05:00Z"]),
        "open": [2650.0, 2651.0], "high": [2651.0, 2652.0],
        "low": [2649.0, 2650.0], "close": [2650.5, 2651.5],
        "tick_volume": [100, 120], "spread": [15, 16], "real_volume": [0, 0],
        "time_raw_epoch": [1767225600, 1767225900],
        "timestamp_correction_applied_seconds": [0, 0],
    })
    path = save_raw_data(df, "XAUUSD", "M5", output_dir=tmp_path)
    assert path.exists()
    assert len(pd.read_csv(path)) == 2
    assert len(list(tmp_path.glob("*.tmp.*"))) == 0


def test_processed_data_atomic_write_preserves_existing(tmp_path):
    """Failed write in save_processed_data must not destroy existing cleaned files."""
    csv_target = tmp_path / "XAUUSD_M5_clean.csv"
    meta_target = tmp_path / "XAUUSD_M5_clean.meta.json"
    original_csv = "time,open,high,low,close\n2026-01-01T00:00:00+00:00,2650,2651,2649,2650.5\n"
    original_meta = '{"symbol": "XAUUSD", "timeframe": "M5", "original": true}'
    csv_target.write_text(original_csv, encoding="utf-8")
    meta_target.write_text(original_meta, encoding="utf-8")

    df = pd.DataFrame({
        "time": pd.to_datetime(["2026-01-02T00:00:00Z"]),
        "open": [2660.0], "high": [2661.0], "low": [2659.0], "close": [2660.5],
        "tick_volume": [100], "spread": [15], "real_volume": [0],
    })
    # Simulate a crash during json.dump
    with patch("json.dump", side_effect=IOError("write failed")):
        with pytest.raises(IOError):
            save_processed_data(df, "XAUUSD", "M5", output_dir=tmp_path)

    # Existing files must be untouched
    assert csv_target.read_text(encoding="utf-8") == original_csv
    assert meta_target.read_text(encoding="utf-8") == original_meta
    assert len(list(tmp_path.glob("*.tmp.*"))) == 0


# ---------------------------------------------------------------------------
# 12. Distinct timeframe dataset checks
# ---------------------------------------------------------------------------

def test_different_timeframes_produce_different_bar_intervals(monkeypatch):
    """[mock-mt5] M5 bars are 300s apart; H1 bars are 3600s apart."""
    def fake_rates(symbol, tf, start_pos, count):
        interval = {5: 300, 16385: 3600}.get(tf, 300)
        start = 1_769_000_000
        dtype = [
            ("time", "<i8"), ("open", "<f8"), ("high", "<f8"),
            ("low", "<f8"), ("close", "<f8"),
            ("tick_volume", "<u8"), ("spread", "<i4"), ("real_volume", "<u8"),
        ]
        return np.array(
            [(start + i * interval, 2650.0, 2651.0, 2649.0, 2650.5, 100, 15, 0)
             for i in range(count)],
            dtype=dtype,
        )

    fake = MagicMock()
    fake.TIMEFRAME_M5 = 5
    fake.TIMEFRAME_H1 = 16385
    fake.symbol_select.return_value = True
    fake.copy_rates_from_pos.side_effect = fake_rates
    fake.symbol_info_tick.return_value = None
    fake.last_error.return_value = (0, "ok")
    monkeypatch.setattr(loader, "mt5", fake)

    df_m5, _ = fetch_historical_bars("XAUUSD", "M5", n_bars=5)
    df_h1, _ = fetch_historical_bars("XAUUSD", "H1", n_bars=5)
    assert (df_m5["time"].diff().dt.total_seconds().dropna() == 300).all()
    assert (df_h1["time"].diff().dt.total_seconds().dropna() == 3600).all()


def test_ohlc_hash_differs_across_synthetic_timeframes():
    """Two different seeded synthetic datasets must not share the same OHLC hash."""
    df_m5, _ = generate_synthetic_gold_data("XAUUSD", "M5", n_bars=200, seed=10)
    df_h1, _ = generate_synthetic_gold_data("XAUUSD", "H1", n_bars=200, seed=20)
    assert ohlc_hash(df_m5) != ohlc_hash(df_h1)


# ---------------------------------------------------------------------------
# 13. Weekend/session-gap handling
# ---------------------------------------------------------------------------

def test_weekend_gap_classified_correctly():
    times = pd.DatetimeIndex([
        "2026-10-16T16:00:00Z",
        "2026-10-16T17:00:00Z",  # last Friday bar
        "2026-10-18T22:00:00Z",  # first Sunday bar
        "2026-10-18T23:00:00Z",
    ], tz="UTC")
    df = pd.DataFrame({
        "time": times, "open": 2650.0, "high": 2651.0, "low": 2649.0, "close": 2650.5,
    })
    n_wk, n_id, n_night, details = classify_gaps(df, "H1")
    assert n_wk >= 1


def test_intraday_gap_classified_as_outage():
    times = pd.DatetimeIndex([
        "2026-10-14T09:00:00Z",
        "2026-10-14T09:05:00Z",
        "2026-10-14T13:05:00Z",  # 4h gap mid-Wednesday = outage
        "2026-10-14T13:10:00Z",
    ], tz="UTC")
    df = pd.DataFrame({
        "time": times, "open": 2650.0, "high": 2651.0, "low": 2649.0, "close": 2650.5,
    })
    n_wk, n_id, n_night, _ = classify_gaps(df, "M5")
    assert n_id >= 1


def test_short_dataset_no_critical_duplication_warning():
    """A clean short dataset should not trigger cross-timeframe OHLC identity CRITICAL."""
    df = pd.DataFrame({
        "time": pd.date_range("2026-10-14T09:00Z", periods=50, freq="5min", tz="UTC"),
        "open": np.full(50, 2650.0), "high": np.full(50, 2651.0),
        "low": np.full(50, 2649.0), "close": np.full(50, 2650.5),
    })
    report = audit_dataset(df, _good_meta(), "M5")
    critical = [w for w in report["warnings"] if w.startswith("CRITICAL")]
    assert len(critical) == 0


# ---------------------------------------------------------------------------
# 14. SMC and ICT engine compatibility
# ---------------------------------------------------------------------------

def test_smc_engine_accepts_clean_data():
    df = _clean_df(n=200, tf="M5")
    result = analyze_smc(df, config=SMCConfig(swing_window=2))
    assert result is not None
    assert result.total_bars == len(df)


def test_ict_engine_accepts_clean_data():
    df = _clean_df(n=200, tf="M15")
    result = analyze_market_structure(df)
    assert result is not None
    assert result.total_bars == len(df)


def test_smc_engine_does_not_import_ict():
    """SMC must remain independent of the ICT engine."""
    import src.smc.engine as smc_mod
    smc_source = Path(smc_mod.__file__).read_text(encoding="utf-8")
    assert "from src.ict" not in smc_source
    assert "import ict" not in smc_source


def test_ict_engine_does_not_import_smc():
    """ICT must remain independent of the SMC engine."""
    import src.ict.engine as ict_mod
    ict_source = Path(ict_mod.__file__).read_text(encoding="utf-8")
    assert "from src.smc" not in ict_source
    assert "import smc" not in ict_source


def test_both_engines_run_on_same_data():
    """Running both engines on same data must produce independently computed results."""
    df = _clean_df(n=300, tf="M15")
    smc_res = analyze_smc(df, config=SMCConfig())
    ict_res = analyze_market_structure(df)
    assert smc_res.total_bars == ict_res.total_bars == len(df)


# ---------------------------------------------------------------------------
# 15. Provenance: MT5 vs synthetic distinction
# ---------------------------------------------------------------------------

def test_synthetic_generator_marks_is_synthetic_true():
    _, meta = generate_synthetic_gold_data("XAUUSD", "M5", n_bars=10)
    assert meta["is_synthetic"] is True


def test_synthetic_sidecar_is_marked_synthetic(tmp_path):
    df, meta = generate_synthetic_gold_data("XAUUSD", "M5", n_bars=10)
    df_clean, audit = clean_market_data(df)
    _, meta_path = save_processed_data(
        df_clean, "XAUUSD", "M5", output_dir=tmp_path, audit_log=audit, source_metadata=meta,
    )
    sidecar = json.loads(meta_path.read_text())
    assert sidecar["is_synthetic"] is True


def test_synthetic_data_blocks_readiness(tmp_path):
    df, meta = generate_synthetic_gold_data("XAUUSD", "M5", n_bars=100)
    df_clean, audit = clean_market_data(df)
    _, meta_path = save_processed_data(
        df_clean, "XAUUSD", "M5", output_dir=tmp_path, audit_log=audit, source_metadata=meta,
    )
    sidecar = json.loads(meta_path.read_text())
    report = audit_dataset(df_clean, sidecar, "M5")
    result = evaluate_research_readiness({"M5": report}, minimum_bars={"M5": 1})
    assert result["overall_status"] == "BLOCKED"
    assert any("synthetic" in b.lower() for b in result["blockers"])


def test_real_sourced_sidecar_not_marked_synthetic(monkeypatch, tmp_path):
    """[mock-mt5] Real fetch sidecar must not be marked synthetic."""
    monkeypatch.setattr(loader, "mt5", _make_fake_mt5(rates=_make_rates(n=10)))
    df, src_meta = fetch_historical_bars("XAUUSD", "M5", n_bars=10)
    df_clean, audit = clean_market_data(df)
    _, meta_path = save_processed_data(
        df_clean, "XAUUSD", "M5", output_dir=tmp_path, audit_log=audit, source_metadata=src_meta,
    )
    sidecar = json.loads(meta_path.read_text())
    assert sidecar["is_synthetic"] is not True
    assert sidecar["source"] == "MetaTrader 5 API"


def test_readiness_warns_when_execution_specification_is_missing():
    df = _clean_df(n=100, tf="M5")
    meta = _good_meta()
    # No broker execution specification exists in legacy-style metadata.
    report = audit_dataset(df, meta, "M5")
    assert report["execution_specification_status"] == "missing"
    assert "point" in report["missing_execution_specification_fields"]
    assert any("BROKER EXECUTION SPECIFICATIONS INCOMPLETE" in w for w in report["warnings"])


def test_missing_calc_mode_marks_symbol_spec_capture_incomplete(monkeypatch):
    """The capture cannot be labeled complete without a formula mode for risk sizing."""
    fake = _make_fake_mt5(rates=_make_rates(n=10))
    fake.symbol_info.return_value = SimpleNamespace(
        digits=2, point=0.01, trade_contract_size=100.0,
        volume_min=0.01, volume_step=0.01, volume_max=100.0,
        trade_tick_size=0.01, trade_tick_value=1.0,
        trade_tick_value_profit=1.0, trade_tick_value_loss=1.0,
        currency_base="XAU", currency_profit="USD", currency_margin="USD",
        trade_stops_level=0, trade_freeze_level=0, spread=20, spread_float=True,
    )
    monkeypatch.setattr(loader, "mt5", fake)
    _, metadata = fetch_historical_bars("XAUUSD", "M5", n_bars=10)
    assert metadata["execution_specification_status"] == "captured_incomplete"
    assert metadata["execution_specification"]["trade_calc_mode"] is None
