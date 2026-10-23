"""
GoldFlow Phase 3A — Data Readiness & Research Framework Tests.

Covers:
1. Data Provenance & Identity:
   - Synthetic data flag detection from meta.json.
   - Identical OHLC sequence detection across timeframes.
   - UTC timestamp validation.
2. Period Splitting:
   - Strict chronological ordering guarantee (no shuffling).
   - No timestamp overlap between train/val/test.
3. Forward Excursion (MFE/MAE):
   - Verification that only bars AFTER the event index are used.
   - Correct bullish/bearish direction assignment.
   - Boundary conditions (last bar in dataset, zero horizon).
4. Session Classification:
   - Each UTC hour maps to exactly one session label.
5. Leakage Prevention:
   - Event confirmation index is never less than event origin index.
   - Forward excursion uses strictly index > event_bar_index.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.research.data_readiness import (
    audit_all_datasets,
    audit_dataset,
    classify_gaps,
    evaluate_research_readiness,
    load_meta,
    ohlc_hash,
)
from src.research.event_statistics import (
    EventDescriptiveReport,
    PeriodSplit,
    build_structure_break_report,
    classify_session,
    measure_forward_excursion,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

def _make_df(n: int = 50, timeframe_minutes: int = 60, base_price: float = 2650.0, seed: int = 0) -> pd.DataFrame:
    """Make a small UTC-aware OHLC DataFrame with realistic Gold price levels."""
    rng = np.random.default_rng(seed)
    times = pd.date_range(
        start="2026-01-06 00:00:00",   # Monday
        periods=n,
        freq=f"{timeframe_minutes}min",
        tz="UTC",
    )
    prices = base_price + np.cumsum(rng.normal(0, 1.5, size=n))
    rows = []
    for t, p in zip(times, prices):
        body = abs(rng.normal(1.0, 0.5))
        o = round(p, 2)
        c = round(p + rng.uniform(-body, body), 2)
        h = round(max(o, c) + abs(rng.uniform(0.1, 0.5)), 2)
        lo = round(min(o, c) - abs(rng.uniform(0.1, 0.5)), 2)
        rows.append({"time": t, "open": o, "high": h, "low": lo, "close": c})
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Data Provenance & Identity
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataProvenanceAndIdentity:

    def test_synthetic_flag_detected_from_meta(self):
        """audit_dataset must raise a warning when is_synthetic=True in meta."""
        df = _make_df(30)
        meta = {"is_synthetic": True}
        report = audit_dataset(df, meta, "H1")
        assert report["is_synthetic"] is True
        assert any("SYNTHETIC" in w for w in report["warnings"])

    def test_real_data_flag_not_synthetic(self):
        """audit_dataset should not mark data as synthetic when flag is absent or False."""
        df = _make_df(30)
        meta = {"is_synthetic": False}
        report = audit_dataset(df, meta, "H1")
        assert report["is_synthetic"] is False

    def test_ohlc_hash_different_for_different_data(self):
        """Two DataFrames with different OHLC values must produce different hashes."""
        df_a = _make_df(30, seed=1)
        df_b = _make_df(30, seed=2)
        assert ohlc_hash(df_a) != ohlc_hash(df_b)

    def test_ohlc_hash_same_for_same_data(self):
        """The same OHLC values must always hash identically, regardless of index."""
        df_a = _make_df(30, seed=7)
        df_b = df_a.copy().reset_index(drop=True)
        assert ohlc_hash(df_a) == ohlc_hash(df_b)

    def test_duplicate_ohlc_sequences_flagged_across_timeframes(self, tmp_path):
        """
        If two 'processed' CSVs contain identical OHLC sequences,
        audit_all_datasets must add a CRITICAL warning to both.
        This is the defect detected in GoldFlow's current disk data:
        H4, H1, and M5 share the same 200-bar OHLC sequence.
        """
        df = _make_df(20, seed=5)
        for tf in ["H4", "H1"]:
            csv_path = tmp_path / f"XAUUSD_{tf}_clean.csv"
            df.to_csv(csv_path, index=False)
            meta_path = tmp_path / f"XAUUSD_{tf}_clean.meta.json"
            meta_path.write_text(json.dumps({"is_synthetic": False}))

        results = audit_all_datasets(str(tmp_path))
        # Both timeframes must warn about identical sequences
        for tf in ["H4", "H1"]:
            warnings = results[tf]["warnings"]
            assert any("IDENTICAL" in w for w in warnings), (
                f"Missing IDENTICAL warning for {tf}: {warnings}"
            )

    def test_utc_timezone_convention_validated(self):
        """audit_dataset should flag the absence of UTC timezone awareness."""
        # Naive (timezone-unaware) timestamps
        df = _make_df(20)
        df["time"] = df["time"].dt.tz_localize(None)
        report = audit_dataset(df, {}, "H1")
        assert report["utc_aware"] is False

    def test_duplicate_timestamps_counted(self):
        """Duplicate timestamps must be counted in the audit report."""
        df = _make_df(20)
        df = pd.concat([df, df.iloc[:3]], ignore_index=True)
        report = audit_dataset(df, {}, "H1")
        assert report["duplicate_timestamps"] == 3

    def test_ohlc_violation_detected(self):
        """A row with high < low must be counted as an OHLC violation."""
        df = _make_df(20)
        df.loc[5, "high"] = df.loc[5, "low"] - 1.0   # Force violation
        report = audit_dataset(df, {}, "H1")
        assert report["ohlc_violations"] >= 1

    def test_gap_analysis_is_blocked_when_timestamp_metadata_is_missing(self):
        """Do not classify weekend/maintenance gaps until timestamp mode is explicit."""
        df = _make_df(50, timeframe_minutes=60)
        report = audit_dataset(df, {"is_synthetic": False}, "H1")
        assert report["gap_analysis_status"] == "BLOCKED_UNTRUSTED_TIMESTAMPS"
        assert any("timestamp integrity" in w.lower() for w in report["warnings"])


    def test_missing_provenance_is_unknown_not_real(self):
        df = _make_df(20)
        report = audit_dataset(df, {}, "H1")
        assert report["is_synthetic"] is None
        assert report["provenance_status"] == "unknown"
        assert any("PROVENANCE UNKNOWN" in w for w in report["warnings"])

    def test_nan_ohlc_is_counted_as_violation(self):
        df = _make_df(20)
        df.loc[4, "high"] = np.nan
        report = audit_dataset(df, {"is_synthetic": False}, "H1")
        assert report["ohlc_violations"] >= 1

# ═══════════════════════════════════════════════════════════════════════════════
# 2. Period Splitting — No Leakage
# ═══════════════════════════════════════════════════════════════════════════════

class TestPeriodSplitNoLeakage:

    def test_chronological_order_preserved(self):
        """Train, val, and test sets must be in strictly ascending time order."""
        df = _make_df(100)
        split = PeriodSplit.from_ratios(df, train_ratio=0.70, val_ratio=0.15)
        assert split.train["time"].is_monotonic_increasing
        assert split.validation["time"].is_monotonic_increasing
        assert split.test["time"].is_monotonic_increasing

    def test_no_timestamp_overlap_between_splits(self):
        """No timestamp should appear in more than one split."""
        df = _make_df(100)
        split = PeriodSplit.from_ratios(df)
        train_times = set(split.train["time"].astype(str))
        val_times = set(split.validation["time"].astype(str))
        test_times = set(split.test["time"].astype(str))
        assert train_times.isdisjoint(val_times), "Train/val overlap"
        assert train_times.isdisjoint(test_times), "Train/test overlap"
        assert val_times.isdisjoint(test_times), "Val/test overlap"

    def test_all_bars_accounted_for(self):
        """Sum of split bars must equal the original bar count."""
        df = _make_df(100)
        split = PeriodSplit.from_ratios(df, train_ratio=0.70, val_ratio=0.15)
        total = len(split.train) + len(split.validation) + len(split.test)
        assert total == len(df)

    def test_train_end_precedes_val_start(self):
        """The last train timestamp must be strictly before the first val timestamp."""
        df = _make_df(100)
        split = PeriodSplit.from_ratios(df)
        if len(split.train) > 0 and len(split.validation) > 0:
            assert split.train["time"].iloc[-1] < split.validation["time"].iloc[0]

    def test_val_end_precedes_test_start(self):
        """The last validation timestamp must be strictly before the first test timestamp."""
        df = _make_df(100)
        split = PeriodSplit.from_ratios(df)
        if len(split.validation) > 0 and len(split.test) > 0:
            assert split.validation["time"].iloc[-1] < split.test["time"].iloc[0]

    def test_single_bar_dataset_does_not_crash(self):
        """A 1-bar dataset must not raise an exception."""
        df = _make_df(1)
        split = PeriodSplit.from_ratios(df)
        assert len(split.train) + len(split.validation) + len(split.test) == 1


    @pytest.mark.parametrize("train_ratio,val_ratio", [(0, 0.2), (0.7, 0.3), (1.1, 0.1), (0.7, -0.1)])
    def test_invalid_ratios_raise(self, train_ratio, val_ratio):
        with pytest.raises(ValueError):
            PeriodSplit.from_ratios(_make_df(100), train_ratio=train_ratio, val_ratio=val_ratio)

# ═══════════════════════════════════════════════════════════════════════════════
# 3. Forward Excursion (MFE/MAE) — No Look-Ahead
# ═══════════════════════════════════════════════════════════════════════════════

class TestForwardExcursionNoLookAhead:

    def test_only_bars_after_event_used(self):
        """
        measure_forward_excursion must NEVER use data at or before event_bar_index.
        We inject a huge spike at the event bar itself — it must not appear in MFE.
        """
        df = _make_df(30)
        event_idx = 10
        # Force event bar high to an extreme value that would dominate MFE if used
        df.loc[event_idx, "high"] = 99999.0
        df.loc[event_idx, "close"] = 2650.0
        exc = measure_forward_excursion(df, event_idx, horizon_bars=10, direction="bullish")
        # MFE is relative to close of event bar; must not include the event bar itself
        assert exc["mfe"] is not None
        assert exc["mfe"] < 99999.0 - 2650.0  # Must not include the spike candle

    def test_mfe_non_negative(self):
        """MFE must be >= 0 for any direction."""
        df = _make_df(50)
        for idx in [5, 10, 20]:
            exc_bull = measure_forward_excursion(df, idx, 5, "bullish")
            exc_bear = measure_forward_excursion(df, idx, 5, "bearish")
            if exc_bull["mfe"] is not None:
                assert exc_bull["mfe"] >= 0.0
            if exc_bear["mfe"] is not None:
                assert exc_bear["mfe"] >= 0.0

    def test_mae_non_negative(self):
        """MAE must be >= 0 for any direction."""
        df = _make_df(50)
        for idx in [5, 10, 20]:
            exc = measure_forward_excursion(df, idx, 5, "bullish")
            if exc["mae"] is not None:
                assert exc["mae"] >= 0.0

    def test_zero_horizon_returns_none_values(self):
        """A horizon of 0 must return None for MFE/MAE (no forward bars)."""
        df = _make_df(30)
        exc = measure_forward_excursion(df, 10, horizon_bars=0, direction="bullish")
        assert exc["mfe"] is None
        assert exc["mae"] is None
        assert exc["bars_available"] == 0

    def test_last_bar_event_returns_none_values(self):
        """An event on the last bar has no forward bars, must return None."""
        df = _make_df(20)
        last_idx = len(df) - 1
        exc = measure_forward_excursion(df, last_idx, horizon_bars=10, direction="bullish")
        assert exc["mfe"] is None
        assert exc["mae"] is None
        assert exc["bars_available"] == 0

    def test_bullish_mfe_uses_highs(self):
        """
        For bullish direction, MFE is measured from event close to maximum high.
        Construct a dataset where we know the exact expected MFE.
        """
        rows = []
        base_time = pd.Timestamp("2026-01-06 00:00:00", tz="UTC")
        for i in range(10):
            rows.append({
                "time": base_time + pd.Timedelta(hours=i),
                "open":  2650.0,
                "high":  2650.0 + (i + 1) * 2.0,   # Highs increase predictably
                "low":   2649.0,
                "close": 2650.0,
            })
        df = pd.DataFrame(rows)
        event_idx = 2   # close = 2650.0
        exc = measure_forward_excursion(df, event_idx, horizon_bars=5, direction="bullish")
        # Forward bars 3..7 have highs: 2658, 2660, 2662, 2664, 2666
        # MFE = max(highs) - ref_close = 2666 - 2650 = 16.0
        assert exc["mfe"] is not None
        assert abs(exc["mfe"] - 16.0) < 0.01

    def test_bearish_mfe_uses_lows(self):
        """
        For bearish direction, MFE is measured from event close to minimum low.
        """
        rows = []
        base_time = pd.Timestamp("2026-01-06 00:00:00", tz="UTC")
        for i in range(10):
            rows.append({
                "time": base_time + pd.Timedelta(hours=i),
                "open":  2650.0,
                "high":  2651.0,
                "low":   2650.0 - (i + 1) * 2.0,   # Lows decrease predictably
                "close": 2650.0,
            })
        df = pd.DataFrame(rows)
        event_idx = 2   # close = 2650.0
        exc = measure_forward_excursion(df, event_idx, horizon_bars=5, direction="bearish")
        # Forward bars 3..7 have lows: 2642, 2640, 2638, 2636, 2634
        # MFE = ref_close - min(lows) = 2650 - 2634 = 16.0
        assert exc["mfe"] is not None
        assert abs(exc["mfe"] - 16.0) < 0.01


    def test_partial_forward_window_is_marked_incomplete(self):
        df = _make_df(10)
        result = measure_forward_excursion(df, 7, horizon_bars=5, direction="bullish")
        assert result["bars_available"] == 2
        assert result["complete_horizon"] is False

    def test_full_forward_window_is_marked_complete(self):
        df = _make_df(10)
        result = measure_forward_excursion(df, 2, horizon_bars=5, direction="bullish")
        assert result["bars_available"] == 5
        assert result["complete_horizon"] is True

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError):
            measure_forward_excursion(_make_df(10), 2, 3, "sideways")

    def test_out_of_range_event_index_raises(self):
        with pytest.raises(IndexError):
            measure_forward_excursion(_make_df(10), 10, 3, "bullish")

    def test_structure_report_uses_explicit_event_direction_and_excludes_partial_horizon(self):
        df = _make_df(10)
        event = SimpleNamespace(direction=SimpleNamespace(value="BEARISH"), break_index=8)
        report = build_structure_break_report(df, [event], "H1", "test", horizon_bars=5)
        assert report.event_count == 1
        assert report.mfe_stats["mean"] is None
        assert report.mae_stats["mean"] is None

# ═══════════════════════════════════════════════════════════════════════════════
# 4. Session Classification
# ═══════════════════════════════════════════════════════════════════════════════

class TestSessionClassification:

    @pytest.mark.parametrize("hour,expected_session", [
        (0,  "Asia"),
        (3,  "Asia"),
        (7,  "Asia"),
        (8,  "London"),
        (11, "London"),
        (12, "NY_AM"),
        (16, "NY_AM"),
        (17, "NY_PM"),
        (20, "NY_PM"),
        (22, "Asia"),
        (23, "Asia"),
    ])
    def test_session_classification_by_hour(self, hour, expected_session):
        ts = pd.Timestamp(f"2026-01-06 {hour:02d}:00:00", tz="UTC")
        assert classify_session(ts) == expected_session, (
            f"Hour {hour}: expected {expected_session}, got {classify_session(ts)}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Gap Classification
# ═══════════════════════════════════════════════════════════════════════════════

class TestGapClassification:

    def test_weekend_gap_detected(self):
        """A gap spanning Friday 21:00 UTC to Sunday 22:00 UTC must be classified as weekend."""
        times = pd.to_datetime([
            "2026-01-09 21:00:00+00:00",   # Friday 21:00
            "2026-01-11 22:00:00+00:00",   # Sunday 22:00
        ])
        df = pd.DataFrame({
            "time": times,
            "open": [2650.0, 2652.0],
            "high": [2651.0, 2653.0],
            "low": [2649.0, 2651.0],
            "close": [2650.5, 2652.5],
        })
        n_wk, n_id, _night, details = classify_gaps(df, "H1")
        assert n_wk >= 1
        assert n_id == 0

    def test_intraday_gap_detected(self):
        """A gap of multiple bars during a weekday must be classified as intraday outage."""
        times = pd.to_datetime([
            "2026-01-07 10:00:00+00:00",   # Wednesday
            "2026-01-07 18:00:00+00:00",   # 8-hour gap (intraday)
        ])
        df = pd.DataFrame({
            "time": times,
            "open": [2650.0, 2652.0],
            "high": [2651.0, 2653.0],
            "low": [2649.0, 2651.0],
            "close": [2650.5, 2652.5],
        })
        n_wk, n_id, _night, details = classify_gaps(df, "H1")
        assert n_id >= 1

    def test_friday_daytime_to_sunday_is_intraday_outage(self):
        """A long outage starting during Friday trading must not be hidden as a weekend closure."""
        times = pd.to_datetime([
            "2026-01-09 10:00:00+00:00",  # Friday daytime
            "2026-01-11 21:00:00+00:00",  # Sunday reopen-like timestamp
        ])
        df = pd.DataFrame({
            "time": times,
            "open": [2650.0, 2652.0], "high": [2651.0, 2653.0],
            "low": [2649.0, 2651.0], "close": [2650.5, 2652.5],
        })
        n_wk, n_id, _night, details = classify_gaps(df, "H1")
        assert n_wk == 0
        assert n_id == 1

    def test_normal_intervals_not_classified_as_gaps(self):
        """Consecutive hourly bars must produce zero gaps."""
        df = _make_df(20, timeframe_minutes=60)
        n_wk, n_id, _night, details = classify_gaps(df, "H1")
        # All 20 bars are consecutive hours on the same weekday — no gaps expected
        assert n_wk == 0
        assert n_id == 0


class TestResearchReadinessGates:
    def test_unknown_provenance_blocks_research(self):
        df = _make_df(50)
        report = audit_dataset(df, {}, "H1")
        report["ohlc_hash"] = ohlc_hash(df)
        readiness = evaluate_research_readiness({"H1": report}, minimum_bars={"H1": 10})
        assert readiness["overall_status"] == "BLOCKED"
        assert any("source is not positively identified" in b for b in readiness["blockers"])

    def test_explicit_real_source_and_sufficient_bars_can_pass(self):
        audits = {}
        for i, tf in enumerate(["H4", "H1", "M15", "M5"]):
            df = _make_df(100, timeframe_minutes=[240, 60, 15, 5][i], seed=10 + i)
            report = audit_dataset(
                df,
                {
                    "source": "MetaTrader 5 API",
                    "is_synthetic": False,
                    "timestamp_mode": "posix_utc",
                    "timestamp_mode_verified": True,
                    "timestamp_integrity_status": "verified",
                    "raw_timestamp_epoch_preserved": True,
                    "retrieval_date_utc": "2026-02-01T00:00:00+00:00",
                    "server_timezone": None,
                },
                tf,
            )
            report["ohlc_hash"] = ohlc_hash(df)
            audits[tf] = report
        # Explicitly use small test thresholds; production defaults remain higher.
        readiness = evaluate_research_readiness(
            audits, minimum_bars={"H4": 10, "H1": 10, "M15": 10, "M5": 10}
        )
        assert readiness["timeframes"]["H1"]["provenance_status"] == "real_source_declared"
        assert readiness["overall_status"] in {"READY_FOR_DESCRIPTIVE_RESEARCH", "READY_WITH_WARNINGS"}

    def test_missing_required_timeframe_blocks_research(self):
        readiness = evaluate_research_readiness({}, minimum_bars={"H4": 10})
        assert readiness["overall_status"] == "BLOCKED"
        assert "H4" in readiness["missing_timeframes"]


    def test_is_synthetic_false_without_source_does_not_prove_real_provenance(self):
        df = _make_df(20)
        report = audit_dataset(df, {"is_synthetic": False}, "H1")
        assert report["is_synthetic"] is False
        assert report["provenance_status"] == "non_synthetic_unverified"
