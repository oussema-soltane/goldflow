"""
GoldFlow Phase 3A — Historical Data Provenance & Integrity Checker.

Performs pre-analysis data readiness audit:
  - Detects synthetic vs. real market data by checking is_synthetic metadata flag.
  - Validates UTC timezone convention, chronological ordering, and OHLC boundaries.
  - Reports available date ranges, bar counts, and gap statistics.
  - Warns when multiple timeframes share identical OHLC sequences (copy-paste error).

No modification of data is performed here; results are returned as a structured dict.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_meta(meta_path: Path) -> Optional[Dict[str, Any]]:
    """Load a .meta.json sidecar file, returning None if missing or invalid."""
    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def ohlc_hash(df: pd.DataFrame) -> str:
    """Return a SHA-256 hash of the OHLC columns only (ignores timestamps)."""
    cols = ["open", "high", "low", "close"]
    available = [c for c in cols if c in df.columns]
    arr = df[available].values.astype(float).tobytes()
    return hashlib.sha256(arr).hexdigest()


def classify_gaps(
    df: pd.DataFrame, timeframe: str, server_timezone: Optional[str] = None
) -> Tuple[int, int, int, List[Dict[str, Any]]]:
    """
    Classify timestamp gaps into expected market closures vs. intraday outages.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with a UTC-aware 'time' column, sorted ascending.
    timeframe : str
        One of 'M5', 'M15', 'H1', 'H4'.

    Returns
    -------
    (n_weekend_gaps, n_intraday_gaps, n_nightly_maintenance_gaps, gap_detail_list)
    """
    tf_minutes = {"M5": 5, "M15": 15, "H1": 60, "H4": 240}
    expected_min = tf_minutes.get(timeframe, 15)

    if len(df) < 2 or "time" not in df.columns:
        return 0, 0, 0, []

    times = df["time"].sort_values().reset_index(drop=True)
    deltas = times.diff().dt.total_seconds().dropna() / 60  # in minutes

    weekend_count = 0
    intraday_count = 0
    nightly_count = 0
    gap_details: List[Dict[str, Any]] = []

    for idx, gap_min in deltas.items():
        if gap_min <= expected_min * 1.5:
            # Normal bar interval (allow 50 % tolerance for DST/broker quirks)
            continue
        t_start = times.iloc[idx - 1]
        t_end = times.iloc[idx]
        # Conservative classification: both endpoints must resemble the normal
        # weekend closure. A gap that starts during Friday trading is an outage,
        # even if data resumes on Sunday.
        gap_hours = float(gap_min) / 60.0
        starts_near_weekend_close = (
            (t_start.weekday() == 4 and t_start.hour >= 17)
            or (t_start.weekday() == 5 and t_start.hour <= 2)
        )
        ends_near_weekend_open = (
            (t_end.weekday() == 6 and t_end.hour >= 20)
            or (t_end.weekday() == 0 and t_end.hour <= 2)
        )
        is_weekend_gap = (
            gap_hours >= 40
            and starts_near_weekend_close
            and ends_near_weekend_open
        )
        # Maintenance is only a suspected pattern when an explicit server
        # timezone is recorded. Do not hard-code UTC+3 across seasons.
        is_nightly_maintenance = False
        if server_timezone and gap_hours <= 3.0:
            local_start = t_start.tz_convert(server_timezone)
            local_end = t_end.tz_convert(server_timezone)
            is_nightly_maintenance = (
                local_start.weekday() < 5
                and local_end.weekday() < 5
                and local_start.hour >= 22
                and local_end.hour <= 2
            )
        if is_nightly_maintenance:
            gap_type = "nightly_maintenance"
        elif is_weekend_gap:
            gap_type = "weekend"
        else:
            gap_type = "intraday_outage"

        entry = {
            "start": t_start.isoformat(),
            "end": t_end.isoformat(),
            "gap_minutes": round(gap_min, 1),
            "type": gap_type,
        }
        gap_details.append(entry)
        if is_weekend_gap:
            weekend_count += 1
        elif is_nightly_maintenance:
            nightly_count += 1
        else:
            intraday_count += 1

    return weekend_count, intraday_count, nightly_count, gap_details


def audit_dataset(
    df: pd.DataFrame,
    meta: Optional[Dict[str, Any]],
    timeframe: str,
) -> Dict[str, Any]:
    """
    Produce a structured readiness audit for a single cleaned dataset.

    Returns a dict with keys:
      - is_synthetic, row_count, date_range, utc_aware, monotonic,
        duplicate_timestamps, ohlc_violations, zero_neg_prices,
        weekend_gaps, intraday_gaps, nightly_maintenance_gaps, gap_details, warnings.
    """
    warnings: List[str] = []
    report: Dict[str, Any] = {}

    # ── Synthetic flag ────────────────────────────────────────────────────────
    # Provenance is tri-state: missing metadata is UNKNOWN, not proof of real data.
    synthetic_flag = meta.get("is_synthetic") if meta else None
    source = str(meta.get("source", "")).strip().lower() if meta else ""
    if synthetic_flag is True:
        is_synthetic: Optional[bool] = True
        provenance_status = "synthetic"
        warnings.append(
            "DATA IS SYNTHETIC — generated by the offline benchmark tool. "
            "Results derived from this data must not be presented as real-market findings."
        )
    elif "metatrader 5 api" in source or source in {"mt5", "metatrader5"}:
        is_synthetic = False
        provenance_status = "real_source_declared"
    elif synthetic_flag is False:
        is_synthetic = False
        provenance_status = "non_synthetic_unverified"
        warnings.append(
            "DATA SOURCE UNVERIFIED — metadata says the dataset is not synthetic but does not identify a broker/source. "
            "Do not treat this flag alone as proof of real-market provenance."
        )
    else:
        is_synthetic = None
        provenance_status = "unknown"
        warnings.append(
            "DATA PROVENANCE UNKNOWN — metadata does not establish whether this dataset is synthetic or broker-sourced. "
            "Do not report it as real-market data until provenance is verified."
        )
    report["is_synthetic"] = is_synthetic
    report["provenance_status"] = provenance_status

    timestamp_mode = meta.get("timestamp_mode") if meta else None
    timestamp_status = meta.get("timestamp_integrity_status") if meta else None
    timestamp_mode_verified = bool(meta.get("timestamp_mode_verified", False)) if meta else False
    report["timestamp_mode"] = timestamp_mode
    report["timestamp_integrity_status"] = timestamp_status
    report["timestamp_mode_verified"] = timestamp_mode_verified
    report["server_timezone"] = meta.get("server_timezone") if meta else None
    report["source_verification_status"] = meta.get("source_verification_status") if meta else None
    execution_spec = meta.get("execution_specification") if meta else None
    report["execution_specification_status"] = (
        execution_spec.get("status")
        if isinstance(execution_spec, dict)
        else (meta.get("execution_specification_status", "missing") if meta else "missing")
    )
    report["execution_specification"] = execution_spec if isinstance(execution_spec, dict) else None
    required_execution_fields = (
        "digits", "point", "trade_contract_size", "volume_min", "volume_step",
        "volume_max", "trade_tick_size",
    )
    missing_execution_fields = [
        name for name in required_execution_fields
        if not isinstance(execution_spec, dict) or execution_spec.get(name) is None
    ]
    report["missing_execution_specification_fields"] = missing_execution_fields
    if missing_execution_fields:
        warnings.append(
            "BROKER EXECUTION SPECIFICATIONS INCOMPLETE — missing "
            + ", ".join(missing_execution_fields)
            + ". Price-point size, contract size, and volume constraints must be confirmed from the intended MT5 symbol_info before treating P&L as broker-calibrated."
        )
    elif report["execution_specification_status"] != "captured_complete":
        warnings.append(
            "BROKER EXECUTION SPECIFICATIONS STATUS IS NOT COMPLETE — inspect the captured metadata before calibrating a backtest."
        )
    report["raw_timestamp_epoch_preserved"] = (
        bool(meta.get("raw_timestamp_epoch_preserved", False)) if meta else False
    )
    if timestamp_status != "verified" or not timestamp_mode_verified:
        warnings.append(
            "TIMESTAMP INTEGRITY BLOCKER — the selected timestamp mode has not been "
            "explicitly verified against a live diagnostic. Legacy, unknown, or merely "
            "normalized datasets must remain blocked for time-based research."
        )
    if timestamp_mode == "server_wall_clock" and not report["server_timezone"]:
        warnings.append(
            "TIMESTAMP CONFIGURATION BLOCKER — server_wall_clock mode has no IANA server_timezone."
        )
    if timestamp_mode not in {"posix_utc", "server_wall_clock"}:
        warnings.append(
            "TIMESTAMP CONFIGURATION BLOCKER — timestamp_mode is missing or unsupported."
        )

    # ── Basic shape ───────────────────────────────────────────────────────────
    report["row_count"] = len(df)
    if "time" in df.columns:
        report["date_range"] = {
            "start": str(df["time"].min()),
            "end": str(df["time"].max()),
        }
        report["utc_aware"] = hasattr(df["time"].dtype, "tz") and df["time"].dtype.tz is not None
        retrieval_value = meta.get("retrieval_date_utc") if meta else None
        if retrieval_value:
            try:
                retrieval_ts = pd.Timestamp(retrieval_value)
                if retrieval_ts.tzinfo is None:
                    retrieval_ts = retrieval_ts.tz_localize("UTC")
                else:
                    retrieval_ts = retrieval_ts.tz_convert("UTC")
                times_utc = pd.to_datetime(df["time"], utc=True, errors="coerce")
                future_mask = times_utc > retrieval_ts + pd.Timedelta(minutes=5)
                report["future_candle_count"] = int(future_mask.sum())
                if report["future_candle_count"]:
                    warnings.append(
                        f"{report['future_candle_count']} candle(s) occur more than 5 minutes "
                        "after the recorded retrieval time."
                    )
            except Exception:
                report["future_candle_count"] = None
                warnings.append("Could not validate candle timestamps against retrieval_date_utc.")
        else:
            report["future_candle_count"] = None
            warnings.append("No retrieval_date_utc available; future-candle integrity cannot be checked.")
        report["monotonic"] = bool(df["time"].is_monotonic_increasing)
        report["duplicate_timestamps"] = int(df.duplicated(subset="time").sum())
        if report["duplicate_timestamps"] > 0:
            warnings.append(f"{report['duplicate_timestamps']} duplicate timestamps detected.")
        if not report["monotonic"]:
            warnings.append("Timestamps are NOT monotonically increasing.")
    else:
        warnings.append("Column 'time' is missing from the dataset.")

    # ── OHLC validity ─────────────────────────────────────────────────────────
    ohlc = ["open", "high", "low", "close"]
    if all(c in df.columns for c in ohlc):
        numeric_ohlc = df[ohlc].apply(pd.to_numeric, errors="coerce")
        non_finite = ~np.isfinite(numeric_ohlc.to_numpy(dtype=float)).all(axis=1)
        bad_geometry = (
            (numeric_ohlc["high"] < numeric_ohlc["low"])
            | (numeric_ohlc["high"] < numeric_ohlc["open"])
            | (numeric_ohlc["high"] < numeric_ohlc["close"])
            | (numeric_ohlc["low"] > numeric_ohlc["open"])
            | (numeric_ohlc["low"] > numeric_ohlc["close"])
        ).fillna(True).to_numpy()
        bad = df[non_finite | bad_geometry]
        report["ohlc_violations"] = int(len(bad))
        if report["ohlc_violations"] > 0:
            warnings.append(f"{report['ohlc_violations']} OHLC boundary violations found.")

        zeros = df[(df[ohlc] <= 0).any(axis=1)]
        report["zero_neg_prices"] = int(len(zeros))
        if report["zero_neg_prices"] > 0:
            warnings.append(f"{report['zero_neg_prices']} rows with zero or negative prices.")

        report["price_range"] = {
            "close_min": float(df["close"].min()),
            "close_max": float(df["close"].max()),
            "close_std": float(df["close"].std()),
        }
    else:
        warnings.append("One or more OHLC columns missing.")

    # ── Gap analysis ──────────────────────────────────────────────────────────
    if "time" in df.columns:
        if timestamp_status != "verified" or not timestamp_mode_verified or timestamp_mode not in {"posix_utc", "server_wall_clock"}:
            n_wk, n_id, n_night, gap_details = 0, 0, 0, []
            report["gap_analysis_status"] = "BLOCKED_UNTRUSTED_TIMESTAMPS"
            warnings.append("Gap classification skipped because timestamp integrity is not trusted.")
        else:
            n_wk, n_id, n_night, gap_details = classify_gaps(
                df, timeframe, server_timezone=report.get("server_timezone")
            )
            report["gap_analysis_status"] = "ANALYZED_WITH_ASSUMPTIONS"
        report["weekend_gaps"] = n_wk
        report["intraday_gaps"] = n_id
        report["nightly_maintenance_gaps"] = n_night
        report["gap_details"] = gap_details
        if n_id > 0:
            warnings.append(f"{n_id} intraday gap(s) detected (potential data outage).")
        if n_wk == 0 and len(df) >= 50 and report.get("gap_analysis_status") != "BLOCKED_UNTRUSTED_TIMESTAMPS":
            warnings.append(
                "No weekend gaps detected in a dataset with >50 bars. "
                "This suggests the data may be synthetic (continuous timestamp sequence) "
                "or a very short intraday window covering no weekends."
            )

    report["warnings"] = warnings
    return report


def audit_all_datasets(data_dir: str = "data/processed") -> Dict[str, Dict[str, Any]]:
    """
    Scan the processed data directory and run audit_dataset on all found CSVs.

    Returns a mapping of timeframe -> audit_report.
    """
    results: Dict[str, Dict[str, Any]] = {}
    base = Path(data_dir)
    for csv_path in sorted(base.glob("*_clean.csv")):
        meta_path = csv_path.with_suffix(".meta.json").with_name(
            csv_path.stem + ".meta.json"
        )
        meta = load_meta(meta_path)
        # Infer timeframe from filename
        import re
        match = re.search(r"_(M5|M15|H1|H4)_clean$", csv_path.stem, flags=re.IGNORECASE)
        timeframe = match.group(1).upper() if match else "UNKNOWN"
        df = pd.read_csv(csv_path, parse_dates=["time"])
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], utc=True)
        results[timeframe] = audit_dataset(df, meta, timeframe)
        results[timeframe]["ohlc_hash"] = ohlc_hash(df)
        results[timeframe]["filename"] = csv_path.name

    # Cross-check for identical OHLC sequences across timeframes
    hashes: Dict[str, str] = {tf: r["ohlc_hash"] for tf, r in results.items()}
    for tf_a, h_a in hashes.items():
        for tf_b, h_b in hashes.items():
            if tf_a < tf_b and h_a == h_b:
                msg = (
                    f"CRITICAL: {tf_a} and {tf_b} have IDENTICAL OHLC sequences "
                    f"(hash={h_a[:12]}…). The data is the same sequence assigned "
                    "different timestamps and is unsuitable for multi-timeframe research."
                )
                results[tf_a]["warnings"].append(msg)
                results[tf_b]["warnings"].append(msg)

    return results


DEFAULT_MINIMUM_BARS = {"H4": 2000, "H1": 5000, "M15": 5000, "M5": 5000}

def evaluate_research_readiness(
    audit_results: Dict[str, Dict[str, Any]],
    minimum_bars: Optional[Dict[str, int]] = None,
    required_timeframes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Decide whether audited datasets meet the minimum gates for Phase 3B
    descriptive research. This does not establish profitability or data authenticity.
    """
    if required_timeframes is not None:
        required = {
            str(tf).upper(): (minimum_bars or {}).get(tf, DEFAULT_MINIMUM_BARS.get(tf, 100))
            for tf in required_timeframes
        }
    else:
        required = dict(DEFAULT_MINIMUM_BARS)
        if minimum_bars:
            required.update({str(k).upper(): int(v) for k, v in minimum_bars.items()})

    dataset_results: Dict[str, Any] = {}
    all_blockers: List[str] = []
    for timeframe, report in sorted(audit_results.items()):
        blockers: List[str] = []
        warnings = list(report.get("warnings", []))
        if report.get("provenance_status") != "real_source_declared":
            blockers.append("Data source is not positively identified as broker/MT5 data.")
        if report.get("timestamp_integrity_status") != "verified" or not report.get("timestamp_mode_verified", False):
            blockers.append("Timestamp conversion is not verified against the live diagnostic; re-ingest and explicitly confirm the selected mode.")
        if report.get("timestamp_mode") not in {"posix_utc", "server_wall_clock"}:
            blockers.append("Timestamp mode is missing or unsupported.")
        if not report.get("raw_timestamp_epoch_preserved", False):
            blockers.append("Original raw MT5 epoch values are not preserved; re-download auditable source data.")
        if report.get("timestamp_mode") == "server_wall_clock" and not report.get("server_timezone"):
            blockers.append("server_wall_clock mode requires an IANA server_timezone.")
        if report.get("future_candle_count") is None:
            blockers.append("Could not verify latest candle against recorded retrieval time.")
        elif report.get("future_candle_count", 0) > 0:
            blockers.append("Future candles exist relative to recorded retrieval time.")
        if report.get("is_synthetic") is True:
            blockers.append("Dataset is explicitly marked synthetic.")
        if report.get("row_count", 0) < required.get(timeframe, 0):
            blockers.append(
                f"Insufficient history: {report.get('row_count', 0)} bars; "
                f"recommended minimum is {required.get(timeframe, 0)}."
            )
        if not report.get("utc_aware", False):
            blockers.append("Timestamps are not UTC-aware.")
        if not report.get("monotonic", False):
            blockers.append("Timestamps are not chronologically ordered.")
        if report.get("duplicate_timestamps", 0):
            blockers.append("Duplicate timestamps are present.")
        if report.get("ohlc_violations", 0):
            blockers.append("Invalid or non-finite OHLC rows are present.")
        if report.get("zero_neg_prices", 0):
            blockers.append("Zero or negative prices are present.")
        critical_identity = [w for w in warnings if w.startswith("CRITICAL:")]
        if critical_identity:
            blockers.append("OHLC sequence duplicates another timeframe; multi-timeframe research is invalid.")
        dataset_results[timeframe] = {
            "status": "BLOCKED" if blockers else ("REVIEW" if warnings else "READY"),
            "row_count": report.get("row_count", 0),
            "minimum_bars": required.get(timeframe),
            "provenance_status": report.get("provenance_status", "unknown"),
            "timestamp_mode": report.get("timestamp_mode"),
            "timestamp_integrity_status": report.get("timestamp_integrity_status"),
            "timestamp_mode_verified": report.get("timestamp_mode_verified"),
            "server_timezone": report.get("server_timezone"),
            "source_verification_status": report.get("source_verification_status"),
            "execution_specification_status": report.get("execution_specification_status"),
            "missing_execution_specification_fields": report.get("missing_execution_specification_fields", []),
            "raw_timestamp_epoch_preserved": report.get("raw_timestamp_epoch_preserved"),
            "future_candle_count": report.get("future_candle_count"),
            "date_range": report.get("date_range"),
            "ohlc_hash": report.get("ohlc_hash"),
            "blockers": blockers,
            "warnings": warnings,
        }
        all_blockers.extend([f"{timeframe}: {item}" for item in blockers])

    missing_timeframes = [tf for tf in required if tf not in audit_results]
    for tf in missing_timeframes:
        all_blockers.append(f"{tf}: required timeframe dataset is missing.")

    any_warnings = any(item.get("warnings") for item in dataset_results.values())
    overall_status = "BLOCKED" if all_blockers else (
        "READY_WITH_WARNINGS" if any_warnings else "READY_FOR_DESCRIPTIVE_RESEARCH"
    )
    return {
        "overall_status": overall_status,
        "research_type": "descriptive ICT event statistics only; not a strategy backtest",
        "timeframes": dataset_results,
        "missing_timeframes": missing_timeframes,
        "blockers": all_blockers,
        "minimum_bars_policy": required,
    }
