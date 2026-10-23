"""
Automated Historical Market Data Download & Pipeline Script for GoldFlow.

Usage:
    python scripts/download_data.py [--symbol XAUUSD] [--timeframes H4,H1,M15,M5] [--bars 5000] [--synthetic]

Features:
- Verifies MT5 connection & discovers available gold instruments.
- Fail-closed transactional data replacement: stages candidate files, validates
  provenance, raw epochs, UTC monotonicity, OHLC geometry, future candles, and row count
  before atomic promotion with automatic rollback.
- Explicit per-timeframe status accounting and nonzero exit codes on any failure.
- Captures and preserves timestamp diagnostic evidence.
- Cleans and stores datasets in data/processed/ with provenance sidecars.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple
import uuid

import numpy as np
import pandas as pd

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.cleaner import clean_market_data, compute_file_sha256, save_processed_data
from src.data.loader import (
    check_mt5_status,
    discover_gold_symbols,
    fetch_historical_bars,
    generate_synthetic_gold_data,
    sanitize_symbol_for_filename,
    save_raw_data,
    shutdown_mt5,
)
from src.data.validator import validate_market_data


def verify_diagnostic_evidence(
    symbol: str,
    timestamp_mode: str,
    server_timezone: Optional[str],
    diagnostic_path: Path = Path("reports/mt5_timestamp_diagnostic.json"),
) -> Dict[str, Any]:
    """
    Verify that an empirical diagnostic run exists and supports the specified mode.
    Returns diagnostic evidence dictionary to attach to acquisition metadata.
    """
    if timestamp_mode != "server_wall_clock":
        return {}

    if not diagnostic_path.is_file():
        raise ValueError(
            f"Timestamp mode is 'server_wall_clock' with verification requested, but no "
            f"diagnostic report was found at {diagnostic_path}. Run scripts/diagnose_mt5_timestamps.py first."
        )

    try:
        with open(diagnostic_path, "r", encoding="utf-8") as f:
            diag = json.load(f)
    except Exception as exc:
        raise ValueError(f"Failed to read diagnostic report {diagnostic_path}: {exc}") from exc

    diag_sym = str(diag.get("symbol", "")).upper()
    target_sym = symbol.upper()
    if diag_sym != target_sym:
        raise ValueError(
            f"Diagnostic report symbol mismatch: report is for {diag_sym!r}, target is {target_sym!r}."
        )

    rec = diag.get("recommendation")
    if rec != "server_wall_clock":
        raise ValueError(
            f"Diagnostic report recommendation is {rec!r}, not 'server_wall_clock'. "
            f"Cannot claim timestamp_mode_verified=True without diagnostic confirmation."
        )

    diag_tz = diag.get("server_timezone_candidate")
    if server_timezone and diag_tz and diag_tz.lower() != server_timezone.lower():
        raise ValueError(
            f"Diagnostic report server timezone candidate ({diag_tz!r}) does not match requested ({server_timezone!r})."
        )

    return {
        "diagnostic_report_file": str(diagnostic_path),
        "recommendation": rec,
        "recommendation_confidence": diag.get("recommendation_confidence"),
        "server_timezone_candidate": diag_tz or server_timezone,
        "server_wall_clock_age_seconds": diag.get("server_wall_clock_age_seconds"),
        "reference_utc_midpoint": diag.get("reference_utc_midpoint"),
        "diagnostic_run_finished_utc": diag.get("run_finished_utc"),
        "verified_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def validate_download_candidate(
    df_raw: pd.DataFrame,
    df_clean: pd.DataFrame,
    meta: Dict[str, Any],
    timeframe: str,
    requested_bars: int,
    symbol: str,
) -> None:
    """
    Comprehensive validation gate for a newly downloaded candidate dataset.
    Raises ValueError with explicit reason if any check fails.
    """
    # 1. Row count verification
    raw_count = len(df_raw)
    clean_count = len(df_clean)
    if raw_count < requested_bars:
        raise ValueError(
            f"Insufficient raw history retrieved for {symbol} {timeframe}: {raw_count:,} < requested {requested_bars:,} bars."
        )
    if clean_count < requested_bars:
        raise ValueError(
            f"Insufficient clean history after cleaning for {symbol} {timeframe}: {clean_count:,} < requested {requested_bars:,} bars."
        )

    # 2. Time column presence and UTC awareness
    if "time" not in df_clean.columns:
        raise ValueError(f"Cleaned dataset for {symbol} {timeframe} is missing required 'time' column.")
    if not hasattr(df_clean["time"].dtype, "tz") or df_clean["time"].dtype.tz is None:
        raise ValueError(f"Cleaned dataset for {symbol} {timeframe} timestamps are not UTC-aware.")

    # 3. Strict monotonicity and uniqueness
    if not df_clean["time"].is_monotonic_increasing:
        raise ValueError(f"Cleaned dataset for {symbol} {timeframe} timestamps are not monotonically increasing.")
    if df_clean["time"].duplicated().any():
        dups = int(df_clean["time"].duplicated().sum())
        raise ValueError(f"Cleaned dataset for {symbol} {timeframe} contains {dups} duplicate timestamp(s).")

    # 4. Future candle check relative to recorded retrieval time
    retrieval_val = meta.get("retrieval_date_utc")
    if retrieval_val:
        try:
            retrieval_ts = pd.Timestamp(retrieval_val)
            if retrieval_ts.tzinfo is None:
                retrieval_ts = retrieval_ts.tz_localize("UTC")
            else:
                retrieval_ts = retrieval_ts.tz_convert("UTC")
            future_mask = df_clean["time"] > (retrieval_ts + pd.Timedelta(minutes=5))
            future_count = int(future_mask.sum())
            if future_count > 0:
                raise ValueError(
                    f"Cleaned dataset for {symbol} {timeframe} contains {future_count} future candle(s) "
                    f"relative to retrieval timestamp ({retrieval_ts}). Latest bar: {df_clean['time'].iloc[-1]}."
                )
        except (ValueError, TypeError) as exc:
            if "future candle" in str(exc):
                raise

    # 5. OHLC price geometry validation
    ohlc = ["open", "high", "low", "close"]
    for col in ohlc:
        if col not in df_clean.columns:
            raise ValueError(f"Cleaned dataset for {symbol} {timeframe} missing OHLC column {col!r}.")

    numeric_ohlc = df_clean[ohlc].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric_ohlc.to_numpy(dtype=float)).all():
        raise ValueError(f"Cleaned dataset for {symbol} {timeframe} contains non-finite price values.")
    if (numeric_ohlc <= 0).any().any():
        raise ValueError(f"Cleaned dataset for {symbol} {timeframe} contains zero or negative prices.")

    bad_geometry = (
        (numeric_ohlc["high"] < numeric_ohlc["low"])
        | (numeric_ohlc["high"] < numeric_ohlc["open"])
        | (numeric_ohlc["high"] < numeric_ohlc["close"])
        | (numeric_ohlc["low"] > numeric_ohlc["open"])
        | (numeric_ohlc["low"] > numeric_ohlc["close"])
    )
    if bad_geometry.any():
        bad_count = int(bad_geometry.sum())
        raise ValueError(f"Cleaned dataset for {symbol} {timeframe} contains {bad_count} OHLC boundary violations.")

    # 6. Raw epoch preservation check
    if "time_raw_epoch" not in df_raw.columns:
        raise ValueError(f"Raw dataset for {symbol} {timeframe} does not contain 'time_raw_epoch' audit column.")
    if not meta.get("raw_timestamp_epoch_preserved"):
        raise ValueError(f"Metadata for {symbol} {timeframe} does not declare raw_timestamp_epoch_preserved=True.")

    # 7. Completed bar check
    if meta.get("incomplete_bar_excluded") is not True:
        raise ValueError(f"Metadata for {symbol} {timeframe} does not declare incomplete_bar_excluded=True.")


def transactionally_stage_and_promote(
    df_raw: pd.DataFrame,
    df_clean: pd.DataFrame,
    meta: Dict[str, Any],
    audit_log: Dict[str, Any],
    symbol: str,
    timeframe: str,
    raw_dir: Path = Path("data/raw"),
    processed_dir: Path = Path("data/processed"),
) -> Tuple[Path, Path, Path]:
    """
    Transactionally save raw CSV, clean CSV, and clean metadata JSON.
    - Staged first to temporary .staging files.
    - Target files backed up to .bak files before promotion.
    - If promotion of any file fails, roll back from .bak files immediately.
    - If promotion succeeds, clean up .bak files.
    """
    safe_symbol = sanitize_symbol_for_filename(symbol)
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    raw_filename = f"{safe_symbol}_{timeframe}_raw.csv"
    clean_filename = f"{safe_symbol}_{timeframe}_clean.csv"
    meta_filename = f"{safe_symbol}_{timeframe}_clean.meta.json"

    raw_target = raw_dir / raw_filename
    clean_target = processed_dir / clean_filename
    meta_target = processed_dir / meta_filename

    tmp_token = uuid.uuid4().hex[:8]
    staging_raw = raw_dir / f".staging_{raw_filename}.{tmp_token}.tmp"
    staging_clean = processed_dir / f".staging_{clean_filename}.{tmp_token}.tmp"
    staging_meta = processed_dir / f".staging_{meta_filename}.{tmp_token}.tmp"

    try:
        # 1. Write staged raw CSV
        df_raw.to_csv(staging_raw, index=False)
        if staging_raw.stat().st_size == 0 and len(df_raw) > 0:
            raise RuntimeError(f"Staged raw file {staging_raw} has zero bytes.")

        # Compute raw SHA256 directly from the staged raw file
        raw_hash = compute_file_sha256(staging_raw)
        meta["raw_file_sha256"] = raw_hash
        meta["raw_source_file"] = raw_filename

        # 2. Write staged clean CSV
        df_clean.to_csv(staging_clean, index=False)
        if staging_clean.stat().st_size == 0 and len(df_clean) > 0:
            raise RuntimeError(f"Staged clean file {staging_clean} has zero bytes.")

        # 3. Assemble and write staged metadata JSON
        now_utc = pd.Timestamp.now(tz="UTC").isoformat()
        meta_to_write = {
            "symbol": symbol,
            "sanitized_symbol": safe_symbol,
            "timeframe": timeframe,
            "processed_file": clean_filename,
            "raw_source_file": raw_filename,
            "raw_file_sha256": raw_hash,
            "raw_row_count": len(df_raw),
            "processed_row_count": len(df_clean),
            "requested_bars": meta.get("requested_bars"),
            "actual_rows_received": meta.get("actual_rows_received", len(df_raw)),
            "duplicates_removed": audit_log.get("duplicates_removed", 0) if audit_log else 0,
            "invalid_ohlc_removed": audit_log.get("invalid_ohlc_removed", 0) if audit_log else 0,
            "processed_date_utc": now_utc,
            "timezone_convention": "UTC (UTC-aware pd.Timestamp)",
            "source": meta.get("source", "MetaTrader 5 API"),
            "is_synthetic": meta.get("is_synthetic", False),
            "broker_server": meta.get("broker_server"),
            "broker_company": meta.get("broker_company"),
            "execution_specification": meta.get("execution_specification"),
            "execution_specification_status": meta.get("execution_specification_status", "missing"),
            "source_verification_status": meta.get(
                "source_verification_status", "declared_not_independently_verified"
            ),
            "raw_timestamp_epoch_preserved": bool(meta.get("raw_timestamp_epoch_preserved", False)),
            "retrieval_date_utc": meta.get("retrieval_date_utc"),
            "incomplete_bar_excluded": meta.get("incomplete_bar_excluded"),
            "timestamp_mode": meta.get("timestamp_mode"),
            "timestamp_representation": meta.get("timestamp_representation"),
            "server_timezone": meta.get("server_timezone"),
            "server_utc_offset_hours": meta.get("server_utc_offset_hours"),
            "timestamp_correction_applied_seconds": meta.get("timestamp_correction_applied_seconds"),
            "timestamp_correction_applied_seconds_min": meta.get("timestamp_correction_applied_seconds_min"),
            "timestamp_correction_applied_seconds_max": meta.get("timestamp_correction_applied_seconds_max"),
            "timestamp_mode_verified": bool(meta.get("timestamp_mode_verified", False)),
            "timestamp_integrity_status": meta.get("timestamp_integrity_status", "unverified"),
            "timestamp_diagnostic_evidence": meta.get("timestamp_diagnostic_evidence"),
            "start_time": df_clean["time"].iloc[0].isoformat() if len(df_clean) > 0 else None,
            "end_time": df_clean["time"].iloc[-1].isoformat() if len(df_clean) > 0 else None,
            "audit_operations": audit_log.get("operations", []) if audit_log else [],
        }

        with open(staging_meta, "w", encoding="utf-8") as f:
            json.dump(meta_to_write, f, indent=2)
        if staging_meta.stat().st_size == 0:
            raise RuntimeError(f"Staged metadata file {staging_meta} has zero bytes.")

    except Exception:
        for p in [staging_raw, staging_clean, staging_meta]:
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
        raise

    # 4. Atomic promotion with rollback protection
    backups: Dict[Path, Path] = {}
    try:
        # Create temporary backups of any existing files
        for target in [raw_target, clean_target, meta_target]:
            if target.exists():
                bak = target.with_suffix(f"{target.suffix}.bak.{tmp_token}")
                shutil.copy2(target, bak)
                backups[target] = bak

        # Atomically replace target files
        os.replace(staging_raw, raw_target)
        os.replace(staging_clean, clean_target)
        os.replace(staging_meta, meta_target)

        # On success, remove temporary backups
        for bak in backups.values():
            if bak.exists():
                try:
                    bak.unlink()
                except OSError:
                    pass

        return raw_target, clean_target, meta_target

    except Exception as exc:
        # Rollback from backups
        for target, bak in backups.items():
            if bak.exists():
                try:
                    os.replace(bak, target)
                except Exception:
                    pass
        for p in [staging_raw, staging_clean, staging_meta]:
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass
        raise RuntimeError(
            f"Atomic promotion failed for {symbol} {timeframe}; existing files safely restored."
        ) from exc


def run_pipeline(
    symbol: Optional[str] = None,
    timeframes: Optional[List[str]] = None,
    bars: int = 2000,
    use_synthetic: bool = False,
    timestamp_mode: str = "posix_utc",
    server_timezone: Optional[str] = None,
    timestamp_mode_verified: bool = False,
    acquisition_summary_path: Optional[Path] = None,
    allow_headless: bool = False,
) -> int:
    """
    Run data download pipeline. Returns integer process exit code:
      0 : Success for all requested timeframes.
      2 : Failure in any requested timeframe or connection issue.

    Parameters
    ----------
    acquisition_summary_path : Path or None
        Override path for the acquisition summary JSON report. Defaults to
        ``reports/data_acquisition_summary.json`` relative to the current
        working directory. Tests should supply a path inside tmp_path to
        prevent contaminating the operational project report.
    """
    if timeframes is None:
        timeframes = ["H4", "H1", "M15", "M5"]
    _summary_path: Path = (
        Path(acquisition_summary_path)
        if acquisition_summary_path is not None
        else Path("reports/data_acquisition_summary.json")
    )

    print("=" * 70)
    print("  GOLDFLOW — HISTORICAL MARKET DATA PIPELINE (PHASE 1 & 3D)")
    print("=" * 70)
    if not use_synthetic:
        print(f"Timestamp mode: {timestamp_mode}")
        print(f"Server timezone: {server_timezone or 'not configured'}")
        print(f"Timestamp mode explicitly verified: {timestamp_mode_verified}")
        if not timestamp_mode_verified:
            print("[WARNING] Research readiness will remain BLOCKED until the live timestamp diagnostic is reviewed.")

    # Synthetic offline branch
    if use_synthetic:
        chosen_symbol = symbol or "XAUUSD"
        print(f"\n[INFO] Running in SYNTHETIC MODE for demonstration/testing.")
        print(f"Target Symbol: {chosen_symbol} | Timeframes: {timeframes} | Bars: {bars}")

        reports = []
        timeframe_results: Dict[str, Any] = {}
        errors: List[str] = []

        for tf in timeframes:
            print(f"\n--> Generating synthetic {chosen_symbol} ({tf})...")
            try:
                df_raw, meta = generate_synthetic_gold_data(symbol=chosen_symbol, timeframe=tf, n_bars=bars)
                raw_path = save_raw_data(df_raw, chosen_symbol, tf)
                print(f"    Raw CSV saved: {raw_path}")

                report = validate_market_data(df_raw, symbol=chosen_symbol, timeframe=tf)
                reports.append(report)

                df_clean, audit = clean_market_data(df_raw, symbol=chosen_symbol, timeframe=tf)
                clean_path, meta_path = save_processed_data(
                    df_clean,
                    chosen_symbol,
                    tf,
                    raw_source_path=raw_path,
                    audit_log=audit,
                    source_metadata=meta,
                )
                print(f"    Cleaned CSV saved: {clean_path} ({len(df_clean):,} bars)")
                print(f"    Provenance sidecar: {meta_path}")
                timeframe_results[tf] = {
                    "status": "SUCCESS",
                    "bars_retrieved": len(df_clean),
                    "bars_requested": bars,
                    "clean_path": str(clean_path),
                    "meta_path": str(meta_path),
                }
            except Exception as exc:
                err_msg = f"Failed synthetic generation for {tf}: {exc}"
                print(f"    [ERROR] {err_msg}")
                errors.append(err_msg)
                timeframe_results[tf] = {
                    "status": "FAILED",
                    "reason": str(exc),
                    "bars_requested": bars,
                }

        if reports:
            primary_report = next((r for r in reports if r.timeframe == "M15"), reports[-1])
            json_path = primary_report.save_json("reports/data_quality_report.json")
            md_path = primary_report.save_markdown("reports/data_quality_report.md")
            print(f"\n[SUCCESS] Reports written:")
            print(f"  - JSON: {json_path}")
            print(f"  - Markdown: {md_path}")

        summary = {
            "pipeline_timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "symbol": chosen_symbol,
            "requested_timeframes": timeframes,
            "requested_bars": bars,
            "use_synthetic": True,
            "overall_status": "FAILED" if errors else "SUCCESS",
            "timeframe_results": timeframe_results,
            "errors": errors,
        }
        _summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(_summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        return 2 if errors else 0

    # Live MT5 branch: check connection
    print("\n[1/4] Checking MetaTrader 5 Connectivity...")
    status = check_mt5_status(require_running_process=not allow_headless)
    if not status["connected"] and status.get("terminal_installed"):
        direct_status = check_mt5_status(require_running_process=False)
        if direct_status.get("connected"):
            print("  [INFO] MT5 desktop GUI process not detected; connected via direct terminal IPC.")
            status = direct_status
    print(f"  - MT5 Package: {'Installed' if status['package_installed'] else 'NOT installed'}")
    print(f"  - Terminal Installed: {'Yes' if status['terminal_installed'] else 'No'}")
    if status['terminal_path']:
        print(f"    Path: {status['terminal_path']}")
    print(f"  - Connection Status: {'CONNECTED' if status['connected'] else 'DISCONNECTED'}")
    print(f"  - Message: {status['actionable_message']}")

    if not status["connected"]:
        print("\n[ERROR] Cannot proceed without a live MT5 connection.")
        return 2

    # Verify diagnostic evidence if timestamp_mode_verified is requested
    diagnostic_evidence: Dict[str, Any] = {}
    if timestamp_mode_verified and timestamp_mode == "server_wall_clock":
        try:
            chosen_sym_check = symbol or "XAUUSD"
            diagnostic_evidence = verify_diagnostic_evidence(
                symbol=chosen_sym_check,
                timestamp_mode=timestamp_mode,
                server_timezone=server_timezone,
            )
            print(f"  - Live timestamp diagnostic verified: {diagnostic_evidence.get('recommendation')} "
                  f"(age: {diagnostic_evidence.get('server_wall_clock_age_seconds')}s)")
        except Exception as exc:
            print(f"\n[ERROR] Timestamp diagnostic verification failed: {exc}")
            return 2

    # Symbol discovery
    print("\n[2/4] Discovering Available Gold Instruments...")
    gold_symbols = discover_gold_symbols()
    if not gold_symbols:
        print("  [WARNING] No gold symbols automatically discovered matching 'XAU' or 'GOLD'.")
        chosen_symbol = symbol or "XAUUSD"
    else:
        print(f"  Found {len(gold_symbols)} candidate symbol(s):")
        for s in gold_symbols:
            vis = "Visible in Market Watch" if s["visible"] else "Not in Market Watch"
            print(f"    * {s['name']:<12} | {s['description']} | Digits: {s['digits']} | Spread: {s['spread']} | {vis}")

        if symbol:
            chosen_symbol = symbol
        else:
            chosen_symbol = gold_symbols[0]["name"]
        print(f"\n  -> Selected instrument: {chosen_symbol}")

    # Historical Data Download with fail-closed transactional replacement
    print(f"\n[3/4] Downloading Historical Bars ({bars} bars per timeframe)...")
    reports = []
    timeframe_results: Dict[str, Any] = {}
    pipeline_errors: List[str] = []

    try:
        for tf in timeframes:
            print(f"\n  Fetching {chosen_symbol} on {tf}...")
            try:
                df_raw, meta = fetch_historical_bars(
                    chosen_symbol,
                    tf,
                    n_bars=bars,
                    exclude_incomplete=True,
                    timestamp_mode=timestamp_mode,
                    server_timezone=server_timezone,
                    timestamp_mode_verified=timestamp_mode_verified,
                )
                actual_count = len(df_raw)
                first_ts = df_raw["time"].iloc[0] if actual_count > 0 else "N/A"
                last_ts = df_raw["time"].iloc[-1] if actual_count > 0 else "N/A"
                print(f"    Retrieved: {actual_count:,} bars (requested {bars:,}) | UTC range: {first_ts} -> {last_ts}")

                # Attach diagnostic evidence if verified
                if diagnostic_evidence:
                    meta["timestamp_diagnostic_evidence"] = diagnostic_evidence

                # Pre-write validation
                report = validate_market_data(df_raw, symbol=chosen_symbol, timeframe=tf)
                reports.append(report)
                print(f"    Quality audit: {report.status} ({report.invalid_ohlc_count} invalid OHLC, {report.duplicate_timestamps_count} dups)")

                if report.status == "FAILED" or report.invalid_ohlc_count > 0 or report.duplicate_timestamps_count > 0:
                    raise ValueError(
                        f"Validation gate failed for {chosen_symbol} {tf}: status={report.status}, "
                        f"invalid_ohlc={report.invalid_ohlc_count}, dups={report.duplicate_timestamps_count}."
                    )

                # Clean candidate dataset
                df_clean, audit = clean_market_data(df_raw, symbol=chosen_symbol, timeframe=tf)

                # Candidate integrity validation
                validate_download_candidate(
                    df_raw=df_raw,
                    df_clean=df_clean,
                    meta=meta,
                    timeframe=tf,
                    requested_bars=bars,
                    symbol=chosen_symbol,
                )

                # Transactional staging and promotion
                raw_path, clean_path, meta_path = transactionally_stage_and_promote(
                    df_raw=df_raw,
                    df_clean=df_clean,
                    meta=meta,
                    audit_log=audit,
                    symbol=chosen_symbol,
                    timeframe=tf,
                )
                print(f"    [PROMOTED] Raw CSV: {raw_path} ({len(df_raw):,} bars)")
                print(f"    [PROMOTED] Clean CSV: {clean_path} ({len(df_clean):,} bars)")
                print(f"    [PROMOTED] Metadata sidecar: {meta_path}")

                timeframe_results[tf] = {
                    "status": "SUCCESS",
                    "bars_requested": bars,
                    "raw_bars_received": len(df_raw),
                    "clean_bars_saved": len(df_clean),
                    "start_time_utc": df_clean["time"].iloc[0].isoformat(),
                    "end_time_utc": df_clean["time"].iloc[-1].isoformat(),
                    "raw_sha256": meta.get("raw_file_sha256"),
                    "timestamp_mode": timestamp_mode,
                    "server_timezone": server_timezone,
                    "timestamp_mode_verified": timestamp_mode_verified,
                }

            except Exception as e:
                err_msg = f"Failed to ingest {chosen_symbol} {tf}: {e}"
                print(f"    [SAFETY GATE REJECTION] {err_msg}")
                print(f"    Existing dataset for {tf} was NOT modified.")
                pipeline_errors.append(err_msg)
                timeframe_results[tf] = {
                    "status": "FAILED",
                    "reason": str(e),
                    "bars_requested": bars,
                }

        # Write reports
        if reports:
            print("\n[4/4] Generating Quality Reports...")
            primary_report = next((r for r in reports if r.timeframe == "M15"), reports[-1])
            json_path = primary_report.save_json("reports/data_quality_report.json")
            md_path = primary_report.save_markdown("reports/data_quality_report.md")
            print(f"  - Machine-readable report: {json_path}")
            print(f"  - Markdown report: {md_path}")

        # Write comprehensive acquisition summary
        summary = {
            "pipeline_timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "symbol": chosen_symbol,
            "requested_timeframes": timeframes,
            "requested_bars": bars,
            "timestamp_mode": timestamp_mode,
            "server_timezone": server_timezone,
            "timestamp_mode_verified": timestamp_mode_verified,
            "diagnostic_evidence": diagnostic_evidence,
            "overall_status": "FAILED" if pipeline_errors else "SUCCESS",
            "timeframe_results": timeframe_results,
            "errors": pipeline_errors,
        }
        _summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(_summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

        print("\n" + "=" * 70)
        if pipeline_errors:
            print(f"  PIPELINE FINISHED WITH FAILURES ({len(pipeline_errors)} error(s))")
            for err in pipeline_errors:
                print(f"   * {err}")
        else:
            print("  PIPELINE EXECUTION COMPLETE (ALL TIMEFRAMES SUCCESSFUL)")
        print("=" * 70)

        return 2 if pipeline_errors else 0

    finally:
        shutdown_mt5()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GoldFlow Market Data Ingestion Pipeline")
    parser.add_argument("--symbol", type=str, default=None, help="Trading symbol (e.g., XAUUSD, GOLD)")
    parser.add_argument("--timeframes", type=str, default="H4,H1,M15,M5", help="Comma-separated timeframes")
    parser.add_argument("--bars", type=int, default=2000, help="Number of historical candles to retrieve")
    parser.add_argument("--synthetic", action="store_true", help="Generate synthetic gold benchmark data (offline)")
    parser.add_argument(
        "--timestamp-mode",
        choices=["posix_utc", "server_wall_clock"],
        default="posix_utc",
        help="Timestamp representation. Default follows MT5 documentation; only use server_wall_clock after feed-specific verification.",
    )
    parser.add_argument(
        "--server-timezone",
        type=str,
        default=None,
        help="IANA timezone required for --timestamp-mode server_wall_clock (e.g. Europe/Athens).",
    )
    parser.add_argument(
        "--confirm-timestamp-mode-verified",
        action="store_true",
        help="Record that you reviewed the live timestamp diagnostic and confirmed the chosen mode/timezone.",
    )
    parser.add_argument(
        "--allow-headless",
        action="store_true",
        help="Connect to MT5 terminal directly via IPC even if desktop process is not detected.",
    )

    args = parser.parse_args()
    tf_list = [t.strip().upper() for t in args.timeframes.split(",") if t.strip()]
    if args.timestamp_mode == "server_wall_clock" and not args.server_timezone:
        parser.error("--server-timezone is required with --timestamp-mode server_wall_clock")

    exit_code = run_pipeline(
        symbol=args.symbol,
        timeframes=tf_list,
        bars=args.bars,
        use_synthetic=args.synthetic,
        timestamp_mode=args.timestamp_mode,
        server_timezone=args.server_timezone,
        timestamp_mode_verified=args.confirm_timestamp_mode_verified,
        allow_headless=args.allow_headless,
    )
    sys.exit(exit_code)
