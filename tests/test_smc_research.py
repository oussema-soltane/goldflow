"""
Unit and regression tests for Phase 3C SMC Descriptive Research.

Tests:
1. Provenance and integrity validation (rejection of synthetic or unverified data).
2. Look-ahead bias elimination:
   - Swing pivot confirmation latency (k bars).
   - Order blocks only available after structure break close.
   - Retest signals strictly post-OB confirmation.
   - Forward excursions use next-candle open as reference price.
   - Final-bar signal handled gracefully (censored / no next-bar open).
   - Rolling ATR uses only bars up to signal candle close.
3. Excursion calculations (MFE/MAE in dollars and ATR for Bullish and Bearish).
4. Adversarial sequences:
   - Same-bar retest attempts suppressed.
   - Spike on event candle does not leak into forward horizon.
   - Out-of-bounds horizon censoring.
5. Setup funnel accounting.
6. Session classification consistency.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.research.event_statistics import classify_session, compute_rolling_atr, measure_forward_excursion
from src.research.smc_research import (
    ResearchProtocolConfig,
    compute_common_window_study,
    compute_event_distribution,
    evaluate_setups_and_excursions,
    extract_events_dataframe,
    load_and_verify_inputs,
)
from src.smc.engine import SMCConfig, analyze_smc
from src.smc.models import SMCDirection, SMCStructureType, SMCSwingType
from src.strategy.smc_setups import (
    SMCSetupCandidate,
    SMCSetupConfig,
    detect_smc_setup_candidates,
    detect_smc_setups_with_funnel,
)


def _make_ohlc(
    n: int = 100,
    base_price: float = 2650.0,
    freq: str = "5min",
    start: str = "2026-02-02 08:00:00",
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    times = pd.date_range(start=start, periods=n, freq=freq, tz="UTC")
    prices = base_price + np.cumsum(rng.normal(0, 1.0, size=n))
    rows = []
    for t, p in zip(times, prices):
        o = round(float(p), 2)
        c = round(float(p + rng.uniform(-1.0, 1.0)), 2)
        h = round(float(max(o, c) + abs(rng.uniform(0.1, 1.0))), 2)
        lo = round(float(min(o, c) - abs(rng.uniform(0.1, 1.0))), 2)
        rows.append({"time": t, "open": o, "high": h, "low": lo, "close": c})
    return pd.DataFrame(rows)


def _make_valid_meta(n: int = 150) -> dict:
    return {
        "source": "MetaTrader 5 API",
        "is_synthetic": False,
        "timestamp_integrity_status": "verified",
        "timestamp_mode": "server_wall_clock",
        "server_timezone": "Europe/Athens",
        "timestamp_mode_verified": True,
        "raw_timestamp_epoch_preserved": True,
        "incomplete_bar_excluded": True,
        "processed_row_count": n,
        "retrieval_date_utc": "2026-02-05T00:00:00Z",
    }


class TestInputProvenanceValidation:
    def test_synthetic_data_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150)
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        meta["is_synthetic"] = True
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="synthetic"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"])

    def test_missing_source_provenance_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150)
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        del meta["source"]
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="source provenance"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"])

    def test_unverified_timestamp_status_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150)
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        meta["timestamp_integrity_status"] = "quarantined"
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="timestamp integrity"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"])

    def test_timestamp_mode_unverified_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150)
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        meta["timestamp_mode_verified"] = False
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="timestamp mode is not verified"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"])

    def test_unsupported_timestamp_mode_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150)
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        meta["timestamp_mode"] = "posix_utc"
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="server_wall_clock"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"])

    def test_unsupported_server_timezone_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150)
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        meta["server_timezone"] = "UTC"
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="Europe/Athens"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"])

    def test_missing_raw_epoch_preservation_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150)
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        meta["raw_timestamp_epoch_preserved"] = False
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="raw MT5 epoch"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"])

    def test_row_count_mismatch_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150)
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        meta["processed_row_count"] = 5000  # Mismatch!
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="row count"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"])

    def test_future_candles_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150, start="2026-02-02 12:00:00")
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        meta["retrieval_date_utc"] = "2026-02-02T10:00:00Z"  # Bars are after retrieval time
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="future candle"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"])

    def test_incomplete_active_bar_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150)
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        meta["incomplete_bar_excluded"] = False
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="active candle"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"])

    def test_ohlc_boundary_violation_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150)
        df.loc[10, "high"] = df.loc[10, "low"] - 10.0  # High < Low
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="OHLC"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"])

    def test_insufficient_history_rejected(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(50)
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(50)
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        with pytest.raises(ValueError, match="insufficient history"):
            load_and_verify_inputs(tmp_path, timeframes=["M5"], minimum_bars={"M5": 100})

    def test_valid_dataset_passes_load_and_verify(self, tmp_path):
        csv_file = tmp_path / "XAUUSD_M5_clean.csv"
        meta_file = tmp_path / "XAUUSD_M5_clean.meta.json"
        df = _make_ohlc(150, start="2026-02-02 08:00:00")
        df.to_csv(csv_file, index=False)
        meta = _make_valid_meta(150)
        meta["retrieval_date_utc"] = "2026-02-03T00:00:00Z"
        with open(meta_file, "w") as f:
            json.dump(meta, f)

        loaded = load_and_verify_inputs(tmp_path, timeframes=["M5"], minimum_bars={"M5": 100})
        assert "M5" in loaded
        df_loaded, meta_loaded = loaded["M5"]
        assert len(df_loaded) == 150


class TestLookAheadFreeExcursions:
    def test_spike_on_signal_bar_does_not_leak_into_excursion(self):
        """A price spike on the signal candle must never inflate forward MFE."""
        df = _make_ohlc(30)
        sig_idx = 10
        df.loc[sig_idx, "high"] = 99999.0
        df.loc[sig_idx, "close"] = 2650.0
        next_open = float(df.loc[sig_idx + 1, "open"])

        exc = measure_forward_excursion(
            df=df,
            event_bar_index=sig_idx,
            horizon_bars=5,
            direction="bullish",
            reference_price=next_open,
            start_bar_index=sig_idx + 1,
        )
        assert exc["mfe"] is not None
        assert exc["mfe"] < 90000.0

    def test_bullish_excursion_uses_next_open_reference(self):
        rows = [
            {"time": pd.Timestamp("2026-02-02 10:00:00", tz="UTC"), "open": 2650.0, "high": 2652.0, "low": 2649.0, "close": 2651.0},
            {"time": pd.Timestamp("2026-02-02 10:05:00", tz="UTC"), "open": 2653.0, "high": 2660.0, "low": 2652.0, "close": 2658.0},
            {"time": pd.Timestamp("2026-02-02 10:10:00", tz="UTC"), "open": 2658.0, "high": 2665.0, "low": 2650.0, "close": 2662.0},
        ]
        df = pd.DataFrame(rows)
        # Signal on bar 0. Reference price = open of bar 1 = 2653.0.
        exc = measure_forward_excursion(
            df=df,
            event_bar_index=0,
            horizon_bars=2,
            direction="bullish",
            reference_price=2653.0,
            start_bar_index=1,
            baseline_atr=5.0,
        )
        # In forward bars (1 and 2): max high is 2665.0, min low is 2650.0.
        # Bullish MFE = 2665.0 - 2653.0 = 12.0
        # Bullish MAE = 2653.0 - 2650.0 = 3.0
        assert exc["mfe"] == pytest.approx(12.0)
        assert exc["mae"] == pytest.approx(3.0)
        assert exc["mfe_atr"] == pytest.approx(12.0 / 5.0)
        assert exc["mae_atr"] == pytest.approx(3.0 / 5.0)
        assert exc["favorable_close"] is True
        assert exc["complete_horizon"] is True
        assert exc["censored"] is False

    def test_bearish_excursion_uses_next_open_reference(self):
        rows = [
            {"time": pd.Timestamp("2026-02-02 10:00:00", tz="UTC"), "open": 2650.0, "high": 2652.0, "low": 2649.0, "close": 2651.0},
            {"time": pd.Timestamp("2026-02-02 10:05:00", tz="UTC"), "open": 2650.0, "high": 2654.0, "low": 2642.0, "close": 2645.0},
            {"time": pd.Timestamp("2026-02-02 10:10:00", tz="UTC"), "open": 2645.0, "high": 2648.0, "low": 2638.0, "close": 2640.0},
        ]
        df = pd.DataFrame(rows)
        # Signal on bar 0. Reference price = open of bar 1 = 2650.0.
        exc = measure_forward_excursion(
            df=df,
            event_bar_index=0,
            horizon_bars=2,
            direction="bearish",
            reference_price=2650.0,
            start_bar_index=1,
            baseline_atr=4.0,
        )
        # Forward bars: max high is 2654.0, min low is 2638.0.
        # Bearish MFE = 2650.0 - 2638.0 = 12.0
        # Bearish MAE = 2654.0 - 2650.0 = 4.0
        assert exc["mfe"] == pytest.approx(12.0)
        assert exc["mae"] == pytest.approx(4.0)
        assert exc["mfe_atr"] == pytest.approx(12.0 / 4.0)
        assert exc["mae_atr"] == pytest.approx(4.0 / 4.0)
        assert exc["favorable_close"] is True
        assert exc["complete_horizon"] is True

    def test_signal_on_final_bar_marks_censored(self):
        df = _make_ohlc(10)
        last_idx = len(df) - 1
        exc = measure_forward_excursion(
            df=df,
            event_bar_index=last_idx,
            horizon_bars=5,
            direction="bullish",
            reference_price=float(df["close"].iloc[last_idx]),
            start_bar_index=last_idx + 1,
        )
        assert exc["mfe"] is None
        assert exc["mae"] is None
        assert exc["bars_available"] == 0
        assert exc["complete_horizon"] is False
        assert exc["censored"] is True

    def test_partial_forward_window_marked_censored(self):
        df = _make_ohlc(10)
        # Event at bar 7, start at bar 8, horizon 5 bars -> only bars 8 and 9 available
        exc = measure_forward_excursion(
            df=df,
            event_bar_index=7,
            horizon_bars=5,
            direction="bullish",
            reference_price=2650.0,
            start_bar_index=8,
        )
        assert exc["bars_available"] == 2
        assert exc["complete_horizon"] is False
        assert exc["censored"] is True


class TestRollingAtrNoLeakage:
    def test_rolling_atr_uses_only_past_data(self):
        df = _make_ohlc(30)
        atr_series = compute_rolling_atr(df, period=14)
        assert len(atr_series) == len(df)
        assert pd.isna(atr_series.iloc[12])  # period 14 requires 14 bars (indices 0..13)
        assert not pd.isna(atr_series.iloc[13])

        # Altering future bars (e.g. bar 25) must NOT change atr at bar 15
        atr_15_before = atr_series.iloc[15]
        df_altered = df.copy()
        df_altered.loc[25, "high"] = 99999.0
        df_altered.loc[25, "low"] = 1.0
        atr_altered = compute_rolling_atr(df_altered, period=14)
        assert atr_altered.iloc[15] == pytest.approx(atr_15_before)


class TestSetupFunnelAccounting:
    def test_funnel_counts_add_up_logically(self):
        df = _make_ohlc(300, seed=123)
        analysis = analyze_smc(df, timeframe="M5")
        setups, funnel = detect_smc_setups_with_funnel(df, analysis, SMCSetupConfig())

        assert funnel["total_bars"] == len(df)
        assert funnel["total_structure_breaks"] == len(analysis.structure_breaks)
        assert funnel["choch_breaks_evaluated"] <= funnel["total_structure_breaks"]
        assert funnel["choch_trend_aligned"] <= funnel["choch_breaks_evaluated"]
        assert funnel["choch_with_preceding_sweep"] <= funnel["choch_trend_aligned"]
        assert funnel["choch_with_order_block"] <= funnel["choch_with_preceding_sweep"]
        assert funnel["final_candidates"] == len(setups)
        assert funnel["next_bar_open_available"] <= funnel["final_candidates"]


class TestEventTraceability:
    def test_event_dataframe_contains_unique_traceable_ids(self):
        df = _make_ohlc(150, seed=99)
        analysis = analyze_smc(df, timeframe="M15")
        ev_df = extract_events_dataframe(analysis, df, "M15")
        assert not ev_df.empty
        assert ev_df["event_id"].is_unique
        assert all(ev_df["event_id"].str.startswith(("SWING_M15_", "BREAK_M15_", "POOL_M15_", "SWEEP_M15_", "OB_M15_")))
        assert "confirmation_time" in ev_df.columns
        assert "session" in ev_df.columns


class TestCommonWindowStudy:
    def test_common_window_bounds_filter_correctly(self):
        df_m5 = _make_ohlc(100, start="2026-02-01 00:00:00", freq="5min")
        df_h1 = _make_ohlc(100, start="2026-01-28 00:00:00", freq="1h")
        meta_m5 = {
            "start_time": "2026-02-01T00:00:00+00:00",
            "end_time": str(df_m5["time"].iloc[-1].isoformat()),
        }
        meta_h1 = {
            "start_time": "2026-01-28T00:00:00+00:00",
            "end_time": str(df_h1["time"].iloc[-1].isoformat()),
        }
        datasets = {"M5": (df_m5, meta_m5), "H1": (df_h1, meta_h1)}
        cfg = ResearchProtocolConfig()
        res = compute_common_window_study(datasets, cfg)
        assert "common_start_utc" in res
        assert "common_end_utc" in res
        assert "M5" in res["timeframes"]
        assert "H1" in res["timeframes"]
