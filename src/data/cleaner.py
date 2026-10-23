"""
Market Data Cleaning & Transformation Engine for GoldFlow.

Applies auditable, transparent cleaning protocols:
- Chronological sorting.
- Deduplication of timestamps without price distortion.
- Elimination of corrupt/invalid OHLC rows (documented in audit log).
- Exclusion of active forming candles.
- Strict data type coercion.
- CRITICAL PRINCIPLE: Zero price interpolation or synthetic fabrication of historical trades.
- Storage in data/processed/.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd

from src.data.loader import sanitize_symbol_for_filename

logger = logging.getLogger(__name__)


def clean_market_data(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    timeframe: str = "M15",
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Clean raw market data without fabricating or interpolating missing prices.
    
    COMPLETED-CANDLE OWNERSHIP NOTE:
    ---------------------------------
    Incomplete/forming candle exclusion is owned by the data extraction layer (`fetch_historical_bars`).
    `clean_market_data` does NOT alter or truncate trailing bars using client-side clocks.
    Its responsibility is data hygiene: deduplication, invalid OHLC removal, sorting, and type coercion.

    Parameters
    ----------
    df : pd.DataFrame
        Raw market dataframe.
    symbol : str
        Asset ticker.
    timeframe : str
        Candle timeframe ('H4', 'H1', 'M15', 'M5').

    Returns
    -------
    Tuple[pd.DataFrame, Dict[str, Any]]
        Cleaned DataFrame and an audit dictionary of operations performed.
    """
    if df.empty:
        return df.copy(), {"status": "empty", "original_rows": 0, "final_rows": 0, "duplicates_removed": 0, "invalid_ohlc_removed": 0, "operations": []}

    audit_log: Dict[str, Any] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "original_rows": len(df),
        "duplicates_removed": 0,
        "invalid_ohlc_removed": 0,
        "final_rows": 0,
        "operations": [],
    }

    clean_df = df.copy()

    # Raw-only audit columns are preserved in data/raw/ but do not belong in the
    # standardized analysis dataset.
    clean_df = clean_df.drop(
        columns=["time_raw_epoch", "timestamp_correction_applied_seconds"],
        errors="ignore",
    )

    # 1. Standardize timestamp to UTC
    clean_df["time"] = pd.to_datetime(clean_df["time"], utc=True)
    audit_log["operations"].append("Standardized 'time' column to datetime64[ns, UTC].")

    # 2. Sort chronologically
    clean_df = clean_df.sort_values(by="time").reset_index(drop=True)
    audit_log["operations"].append("Sorted chronologically in ascending order.")

    # 3. Deduplicate timestamps (keep the first record)
    initial_len = len(clean_df)
    clean_df = clean_df.drop_duplicates(subset=["time"], keep="first").reset_index(drop=True)
    dups_removed = initial_len - len(clean_df)
    audit_log["duplicates_removed"] = dups_removed
    if dups_removed > 0:
        audit_log["operations"].append(f"Dropped {dups_removed} duplicate timestamp(s) (preserved first record).")

    # 4. Filter invalid OHLC boundaries and non-positive/non-finite prices
    ohlc_cols = ["open", "high", "low", "close"]
    for col in ohlc_cols:
        clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce")

    valid_mask = (
        clean_df["open"].notna()
        & clean_df["high"].notna()
        & clean_df["low"].notna()
        & clean_df["close"].notna()
        & (clean_df["open"] > 0)
        & (clean_df["high"] > 0)
        & (clean_df["low"] > 0)
        & (clean_df["close"] > 0)
        & (clean_df["high"] >= clean_df["open"])
        & (clean_df["high"] >= clean_df["close"])
        & (clean_df["low"] <= clean_df["open"])
        & (clean_df["low"] <= clean_df["close"])
        & (clean_df["high"] >= clean_df["low"])
    )

    invalid_count = int((~valid_mask).sum())
    audit_log["invalid_ohlc_removed"] = invalid_count
    if invalid_count > 0:
        clean_df = clean_df[valid_mask].reset_index(drop=True)
        audit_log["operations"].append(
            f"Filtered out {invalid_count} corrupt row(s) violating OHLC boundary constraints."
        )

    # 5. Ensure consistent numeric types
    for col in ["open", "high", "low", "close"]:
        clean_df[col] = clean_df[col].astype(float)

    for vol_col in ["tick_volume", "spread", "real_volume"]:
        if vol_col in clean_df.columns:
            clean_df[vol_col] = pd.to_numeric(clean_df[vol_col], errors="coerce").fillna(0).astype(int)
        else:
            clean_df[vol_col] = 0

    clean_df = clean_df.reset_index(drop=True)
    audit_log["final_rows"] = len(clean_df)
    audit_log["operations"].append("Coerced data types: float64 for prices, int64 for volumes and spreads.")

    return clean_df, audit_log


def compute_file_sha256(filepath: Union[str, Path]) -> Optional[str]:
    """Calculate SHA-256 hash of a file for data provenance tracking."""
    p = Path(filepath)
    if not p.exists() or not p.is_file():
        return None
    sha256 = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def save_processed_data(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    output_dir: Union[str, Path] = "data/processed",
    raw_source_path: Optional[Union[str, Path]] = None,
    audit_log: Optional[Dict[str, Any]] = None,
    source_metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[Path, Path]:
    """
    Save cleaned historical dataset to CSV and generate a JSON metadata sidecar.
    
    Parameters
    ----------
    df : pd.DataFrame
        Cleaned market data.
    symbol : str
        Original broker symbol (e.g. 'XAUUSD', 'XAU/USD').
    timeframe : str
        Timeframe (e.g. 'M15').
    output_dir : str or Path
        Output directory.
    raw_source_path : str or Path, optional
        Path to corresponding raw CSV file for provenance tracing.
    audit_log : dict, optional
        Cleaning audit dictionary returned by clean_market_data.

    Returns
    -------
    Tuple[Path, Path]
        (path_to_cleaned_csv, path_to_metadata_json)
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    safe_symbol = sanitize_symbol_for_filename(symbol)
    csv_filename = f"{safe_symbol}_{timeframe}_clean.csv"
    csv_path = out_path / csv_filename

    # Compute raw file hash if available
    raw_hash = None
    raw_name = None
    if raw_source_path:
        raw_p = Path(raw_source_path)
        if raw_p.exists():
            raw_hash = compute_file_sha256(raw_p)
            raw_name = raw_p.name

    # Determine is_synthetic flag accurately: if source is MT5 and not explicitly synthetic, False
    source_val = (source_metadata or {}).get("source", "unknown")
    is_synth = (source_metadata or {}).get("is_synthetic")
    if is_synth is None and "metatrader" in source_val.lower():
        is_synth = False

    # Build provenance sidecar
    now_utc = pd.Timestamp.now(tz="UTC").isoformat()
    meta = {
        "symbol": symbol,
        "sanitized_symbol": safe_symbol,
        "timeframe": timeframe,
        "processed_file": csv_filename,
        "raw_source_file": raw_name,
        "raw_file_sha256": raw_hash,
        "raw_row_count": audit_log.get("original_rows") if audit_log else None,
        "processed_row_count": len(df),
        "requested_bars": (source_metadata or {}).get("requested_bars"),
        "actual_rows_received": (source_metadata or {}).get("actual_rows_received", len(df)),
        "duplicates_removed": audit_log.get("duplicates_removed", 0) if audit_log else 0,
        "invalid_ohlc_removed": audit_log.get("invalid_ohlc_removed", 0) if audit_log else 0,
        "processed_date_utc": now_utc,
        "timezone_convention": "UTC (UTC-aware pd.Timestamp)",
        "source": source_val,
        "is_synthetic": is_synth,
        "broker_server": (source_metadata or {}).get("broker_server"),
        "broker_company": (source_metadata or {}).get("broker_company"),
        # Preserve captured broker symbol specifications. Missing/old specs remain
        # missing rather than being reconstructed from bar prices.
        "execution_specification": (source_metadata or {}).get("execution_specification"),
        "execution_specification_status": (source_metadata or {}).get(
            "execution_specification_status", "missing"
        ),
        "source_verification_status": (source_metadata or {}).get(
            "source_verification_status",
            "declared_not_independently_verified",
        ),
        "raw_timestamp_epoch_preserved": bool(
            (source_metadata or {}).get("raw_timestamp_epoch_preserved", False)
        ),
        "retrieval_date_utc": (source_metadata or {}).get("retrieval_date_utc"),
        "incomplete_bar_excluded": (source_metadata or {}).get("incomplete_bar_excluded"),
        "timestamp_mode": (source_metadata or {}).get("timestamp_mode"),
        "timestamp_representation": (source_metadata or {}).get("timestamp_representation"),
        "server_timezone": (source_metadata or {}).get("server_timezone"),
        "server_utc_offset_hours": (source_metadata or {}).get("server_utc_offset_hours"),
        "timestamp_correction_applied_seconds": (source_metadata or {}).get("timestamp_correction_applied_seconds"),
        "timestamp_correction_applied_seconds_min": (source_metadata or {}).get("timestamp_correction_applied_seconds_min"),
        "timestamp_correction_applied_seconds_max": (source_metadata or {}).get("timestamp_correction_applied_seconds_max"),
        "timestamp_mode_verified": bool((source_metadata or {}).get("timestamp_mode_verified", False)),
        "timestamp_integrity_status": (source_metadata or {}).get("timestamp_integrity_status", "unverified"),
        "timestamp_diagnostic_evidence": (source_metadata or {}).get("timestamp_diagnostic_evidence"),
        "start_time": df["time"].iloc[0].isoformat() if len(df) > 0 else None,
        "end_time": df["time"].iloc[-1].isoformat() if len(df) > 0 else None,
        "audit_operations": audit_log.get("operations", []) if audit_log else [],
    }

    meta_filename = f"{safe_symbol}_{timeframe}_clean.meta.json"
    meta_path = out_path / meta_filename

    # DATA SAFETY: Write both CSV and JSON atomically via temporary files
    fd_csv, tmp_csv_name = tempfile.mkstemp(dir=out_path, prefix=f"{csv_filename}.tmp.", suffix=".csv")
    try:
        with os.fdopen(fd_csv, "w", newline="", encoding="utf-8") as fh:
            df.to_csv(fh, index=False)
        tmp_csv_path = Path(tmp_csv_name)
        if tmp_csv_path.stat().st_size == 0 and len(df) > 0:
            raise RuntimeError(f"Temp file written for {csv_path} has zero bytes; aborting.")
    except Exception:
        try:
            os.unlink(tmp_csv_name)
        except OSError:
            pass
        raise

    fd_meta, tmp_meta_name = tempfile.mkstemp(dir=out_path, prefix=f"{meta_filename}.tmp.", suffix=".json")
    try:
        with os.fdopen(fd_meta, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)
        tmp_meta_path = Path(tmp_meta_name)
        if tmp_meta_path.stat().st_size == 0:
            raise RuntimeError(f"Temp file written for {meta_path} has zero bytes; aborting.")
    except Exception:
        try:
            os.unlink(tmp_csv_name)
        except OSError:
            pass
        try:
            os.unlink(tmp_meta_name)
        except OSError:
            pass
        raise

    # Atomically replace target files only after complete successful write
    os.replace(tmp_csv_name, csv_path)
    os.replace(tmp_meta_name, meta_path)

    return csv_path, meta_path
